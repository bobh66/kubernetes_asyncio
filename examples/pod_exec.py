# Copyright 2019 The Kubernetes Authors.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""
Shows the functionality of exec using a Busybox container.
"""
import asyncio

from kubernetes_asyncio import config
from kubernetes_asyncio.client import Configuration
from kubernetes_asyncio.client.api import core_v1_api
from kubernetes_asyncio.client.rest import ApiException
from kubernetes_asyncio.stream import stream


async def exec_commands(api_instance):
    name = 'busybox-test'
    resp = None
    try:
        resp = await api_instance.read_namespaced_pod(name=name,
                                                      namespace='default')
    except ApiException as e:
        if e.status != 404:
            print("Unknown error: %s" % e)
            exit(1)

    if not resp:
        print("Pod %s does not exist. Creating it..." % name)
        pod_manifest = {
            'apiVersion': 'v1',
            'kind': 'Pod',
            'metadata': {
                'name': name
            },
            'spec': {
                'containers': [{
                    'image': 'busybox',
                    'name': 'sleep',
                    "args": [
                        "/bin/sh",
                        "-c",
                        "while true;do date;sleep 5; done"
                    ]
                }]
            }
        }
        await api_instance.create_namespaced_pod(body=pod_manifest,
                                                 namespace='default')
        while True:
            resp = await api_instance.read_namespaced_pod(name=name,
                                                          namespace='default')
            if resp.status.phase != 'Pending':
                break
            await asyncio.sleep(1)
        print("Done.")

    # Calling exec and waiting for response
    exec_command = [
        '/bin/sh',
        '-c',
        'echo This message goes to stderr; echo This message goes to stdout']
    # When calling a pod with multiple containers running the target container
    # has to be specified with a keyword argument container=<name>.
    resp = await stream(api_instance.connect_get_namespaced_pod_exec,
                        name,
                        'default',
                        command=exec_command,
                        stderr=True, stdin=False,
                        stdout=True, tty=False)
    print("Response: " + resp)

    # Calling exec interactively
    exec_command = ['/bin/sh']
    resp = await stream(api_instance.connect_get_namespaced_pod_exec,
                        name,
                        'default',
                        command=exec_command,
                        stderr=True, stdin=True,
                        stdout=True, tty=False,
                        _preload_content=False)
    commands = [
        "echo This message goes to stdout",
        "echo \"This message goes to stderr\" >&2",
    ]

    while resp.is_open():
        await resp.update(timeout=1)
        if await resp.peek_stdout():
            print("STDOUT: %s" % await resp.read_stdout())
        if await resp.peek_stderr():
            print("STDERR: %s" % await resp.read_stderr())
        if commands:
            c = commands.pop(0)
            print("Running command... %s\n" % c)
            await resp.write_stdin(c + "\n")
        else:
            break

    await resp.write_stdin("date\n")
    sdate = await resp.readline_stdout(timeout=3)
    print("Server date command returns: %s" % sdate)
    await resp.write_stdin("whoami\n")
    user = await resp.readline_stdout(timeout=3)
    print("Server user is: %s" % user)
    await resp.close()


async def main():
    await config.load_kube_config()
    try:
        c = Configuration().get_default_copy()
    except AttributeError:
        c = Configuration()
        c.assert_hostname = False
    Configuration.set_default(c)
    core_v1 = core_v1_api.CoreV1Api()

    await exec_commands(core_v1)
    await core_v1.api_client.close()

if __name__ == "__main__":
    loop = asyncio.new_event_loop()
    loop.run_until_complete(main())
    loop.close()

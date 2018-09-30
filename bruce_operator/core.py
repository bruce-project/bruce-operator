import time
import json
from uuid import uuid4
from functools import lru_cache

import logme
import kubernetes
import background
from kubeconfig import KubeConfig
from kubernetes.client.configuration import Configuration
from kubernetes.client.api_client import ApiClient

from .env import (
    WATCH_NAMESPACE,
    API_GROUP,
    API_VERSION,
    OPERATOR_IMAGE,
    KUBECONFIG_PATH,
)
from .kubectl import kubectl

# https://github.com/kubernetes-client/python/blob/master/examples/create_thirdparty_resource.md


@logme.log
class Operator:
    def __init__(self, api_client=None):

        # Load Kube configuration into module (ugh).
        try:
            kubernetes.config.load_kube_config()
        except FileNotFoundError:
            pass

        # Setup clients.
        self.client = kubernetes.client.CoreV1Api()
        self.custom_client = kubernetes.client.CustomObjectsApi(self.client.api_client)

        # Ensure resource definitions.
        self.ensure_resource_definitions()
        self.ensure_volumes()
        self.fetch_buildpacks()
        # print(self.installed_buildpacks)
        # exit()

    @property
    def installed_buildpacks(self):

        group = API_GROUP  # str | The custom resource's group name
        version = API_VERSION  # str | The custom resource's version
        namespace = WATCH_NAMESPACE  # str | The custom resource's namespace
        plural = (
            "buildpacks"
        )  # str | The custom resource's plural name. For TPRs this would be lowercase plural kind.
        pretty = (
            "true"
        )  # str | If 'true', then the output is pretty printed. (optional)
        watch = (
            False
        )  # bool | Watch for changes to the described resources and return them as a stream of add, update, and remove notifications. (optional)

        try:
            api_response = self.custom_client.list_namespaced_custom_object(
                group, version, namespace, plural, pretty=pretty, watch=watch
            )
            return api_response["items"]
        except kubernetes.client.rest.ApiException:
            return None

    @property
    def installed_apps(self):
        group = "bruce.kennethreitz.org"  # str | The custom resource's group name
        version = "v1alpha1"  # str | The custom resource's version
        namespace = WATCH_NAMESPACE  # str | The custom resource's namespace
        plural = (
            "apps"
        )  # str | The custom resource's plural name. For TPRs this would be lowercase plural kind.
        pretty = (
            "true"
        )  # str | If 'true', then the output is pretty printed. (optional)
        watch = (
            False
        )  # bool | Watch for changes to the described resources and return them as a stream of add, update, and remove notifications. (optional)

        try:
            api_response = self.custom_client.list_namespaced_custom_object(
                group, version, namespace, plural, pretty=pretty, watch=watch
            )
            return api_response["items"]
        except kubernetes.client.rest.ApiException:
            return None

    def spawn_self(self, cmd, label, env=None):
        if env is None:
            env = {}

        # TODO: ENV
        _hash = uuid4().hex
        return kubectl(
            f"run bruce-operator-{label}-{_hash} --image={OPERATOR_IMAGE} -n {WATCH_NAMESPACE} --restart=Never --quiet=True --record=True --image-pull-policy=Always -- bruce-operator {cmd}"
        )

    def ensure_kube_config(self):
        if IN_KUBERNETES:
            host = os.environ["KUBERNETES_SERVICE_HOST"]
            port = os.environ["KUBERNETES_SERVICE_PORT"]
            conf = KubeConfig()
            kc.set_cluster(
                name='the-cluster',
                server='https://{host}:{port}'
                certificate_authority=CERT_LOCATION,
            )

    def ensure_resource_definitions(self):
        # Create Buildpacks resource.
        self.logger.info("Ensuring Buildpack resource definitions...")
        kubectl(
            f"apply -f ./deploy/buildpack-resource-definition.yml -n {WATCH_NAMESPACE}"
        )

        # Create Apps resource.
        self.logger.info("Ensuring App resource definitions...")
        kubectl(f"apply -f ./deploy/app-resource-definition.yml -n {WATCH_NAMESPACE}")

    def ensure_volumes(self):
        self.logger.info("Ensuring Buildpack volume resource...")
        kubectl(f"apply -f ./deploy/buildpacks-volume.yml -n {WATCH_NAMESPACE}")

    def spawn_fetch_buildpack(self, buildpack_name):
        self.logger.info(f"Pretending to fetch {buildpack_name!r} buildpack!")
        self.spawn_self(f"fetch --buildpack={buildpack_name}", label="fetch")

    def fetch_buildpacks(self):
        for buildpack in self.installed_buildpacks:
            self.spawn_fetch_buildpack(buildpack["metadata"]["name"])

    def watch(self):
        self.logger.info("Pretending to watch...")
        time.sleep(5)


operator = Operator()


def watch():
    while True:
        operator.watch()

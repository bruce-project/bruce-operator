import os
import time
import json
from uuid import uuid4
from functools import lru_cache

import logme
import kubernetes
import delegator
from kubeconfig import KubeConfig
from kubernetes.client.configuration import Configuration
from kubernetes.client.api_client import ApiClient

from .env import (
    WATCH_NAMESPACE,
    API_GROUP,
    API_VERSION,
    OPERATOR_IMAGE,
    KUBECONFIG_PATH,
    IN_KUBERNETES,
    CERT_LOCATION,
    TOKEN_LOCATION,
)
from .kubectl import kubectl

# https://github.com/kubernetes-client/python/blob/master/examples/create_thirdparty_resource.md


@logme.log
class Operator:
    def __init__(self, api_client=None):

        # Ensure that we can load the kubeconfig.
        self.ensure_kubeconfig()

        # Load Kube configuration into module (ugh).
        kubernetes.config.load_kube_config()

        # Setup clients.
        self.client = kubernetes.client.CoreV1Api()
        self.custom_client = kubernetes.client.CustomObjectsApi(self.client.api_client)

        # Ensure resource definitions.
        self.ensure_namespace()
        self.ensure_resource_definitions()
        self.ensure_volumes()
        self.ensure_registry()

        # Fetch all the buildpacks.
        self.spawn_fetch_buildpacks()

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

    def ensure_namespace(self):
        self.logger.info("Ensuring bruce namespace...")
        kubectl(f"apply -f ./deploy/_bruce-namespace.yml")

    def ensure_kubeconfig(self):
        """Ensures that ~/.kube/config exists, when running in Kubernetes."""
        # If we're running in a kubernets cluster...
        if IN_KUBERNETES:
            host = os.environ["KUBERNETES_SERVICE_HOST"]
            port = os.environ["KUBERNETES_SERVICE_PORT"]
            # Create a KubeConfig file.
            kc = KubeConfig()

            # Read in the secret token.
            with open(TOKEN_LOCATION, "r") as f:
                token = f.read()

            # Set the credentials.
            kc.set_credentials(name="child", token=token)
            # Set the cluster information.
            kc.set_cluster(
                name="parent",
                server=f"https://{host}:{port}",
                certificate_authority=CERT_LOCATION,
            )
            # Set the context.
            kc.set_context(name="context", cluster="parent", user="child")
            # Use the context.
            kc.use_context("context")

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

    def spawn_fetch_buildpacks(self):
        self.spawn_self(f"fetch-buildpacks", label="fetch")
        for buildpack in self.installed_buildpacks:
            self.logger.info(f"Pretending to fetch {buildpack_name!r} buildpack!")

    def ensure_registry(self):
        self.logger.info("Ensuring Registry volume...")
        kubectl(f"apply -f ./deploy/registry-data.yml -n {WATCH_NAMESPACE}")

        self.logger.info("Ensuring Registry deployment...")
        kubectl(f"apply -f ./deploy/registry-deployment.yml -n {WATCH_NAMESPACE}")

        self.logger.info("Ensuring Registry service...")
        kubectl(f"apply -f ./deploy/registry-service.yml -n {WATCH_NAMESPACE}")

    def watch(self):
        self.logger.info("Pretending to watch...")
        time.sleep(5)


operator = Operator()


@logme.log
def watch(fork=True, buildpacks=False, apps=False, logger=None):

    if buildpacks and apps:
        raise RuntimeError("Can only watch one at a time: buildpacks and apps.")

    if fork:
        subprocesses = []
        for t in ("apps", "buildpacks"):
            cmd = f"bruce-operator watch --{t}"
            logger.info(f"Running $ {cmd} in the background.")
            c = delegator.run(cmd, block=False)
            subprocesses.append(c)

        logger.info(f"Blocking on subprocesses completion.")
        for subprocess in subprocesses:
            subprocess.block()

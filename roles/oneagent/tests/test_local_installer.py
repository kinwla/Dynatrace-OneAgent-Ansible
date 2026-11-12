import logging

from ansible.config import AnsibleConfigurator
from ansible.runner import AnsibleRunner
from command.platform_command_wrapper import PlatformCommandWrapper
from constants import (
    UNIX_DOWNLOAD_DIR_PATH,
    WINDOWS_DOWNLOAD_DIR_PATH,
    WORK_INSTALLERS_DIR_PATH,
)
from deployment.deployment_operations import (
    check_agent_state,
    check_download_directory,
    enable_for_system_family,
    get_installers,
    perform_operation_on_platforms,
    run_deployment,
    set_ca_cert_download_params,
)
from deployment.deployment_platform import DeploymentPlatform, PlatformCollection


def test_local_installer(
    runner: AnsibleRunner,
    configurator: AnsibleConfigurator,
    platforms: PlatformCollection,
    wrapper: PlatformCommandWrapper,
    installer_server_url: str,
):
    set_ca_cert_download_params(configurator, installer_server_url)

    for platform in platforms:
        installers_location = WORK_INSTALLERS_DIR_PATH
        latest_installer_name = get_installers(platform.system(), platform.arch(), "latest")[-1]
        configurator.set_platform_parameter(
            platform,
            configurator.LOCAL_INSTALLER_KEY,
            f"{installers_location}/{latest_installer_name}",
        )

    _unused = run_deployment(runner, configurator)

    logging.info("Check if agent is installed")
    perform_operation_on_platforms(platforms, check_agent_state, wrapper, True)

    logging.info("Check if installer was removed")
    perform_operation_on_platforms(
        platforms,
        check_download_directory,
        wrapper,
        False,
        UNIX_DOWNLOAD_DIR_PATH,
        WINDOWS_DOWNLOAD_DIR_PATH,
    )


@enable_for_system_family(family="windows")
def test_windows_installer_does_not_use_predictable_path(
    runner: AnsibleRunner,
    configurator: AnsibleConfigurator,
    platforms: PlatformCollection,
    wrapper: PlatformCommandWrapper,
    installer_server_url: str,
):
    # A file planted by a local user at the predictable installer path in the shared temp directory
    # must neither be overwritten nor executed - the installer has to be staged in a private directory
    decoy_path = WINDOWS_DOWNLOAD_DIR_PATH / "Dynatrace-OneAgent-Windows-latest.exe"
    decoy_content = "planted by an unprivileged user"
    windows_hosts = platforms[DeploymentPlatform.WINDOWS_X86]

    set_ca_cert_download_params(configurator, installer_server_url)
    configurator.set_platform_parameter(
        DeploymentPlatform.WINDOWS_X86, configurator.DOWNLOAD_DIR_KEY, str(WINDOWS_DOWNLOAD_DIR_PATH)
    )
    latest_installer_name = get_installers("windows", "x86", "latest")[-1]
    configurator.set_platform_parameter(
        DeploymentPlatform.WINDOWS_X86,
        configurator.LOCAL_INSTALLER_KEY,
        f"{WORK_INSTALLERS_DIR_PATH}/{latest_installer_name}",
    )

    for address in windows_hosts:
        assert wrapper.windows_command_wrapper.write_file(address, decoy_path, decoy_content).returncode == 0

    try:
        _unused = run_deployment(runner, configurator)

        logging.info("Check if agent is installed")
        perform_operation_on_platforms(
            {DeploymentPlatform.WINDOWS_X86: windows_hosts}, check_agent_state, wrapper, True
        )

        logging.info("Check if the planted file was left untouched")
        for address in windows_hosts:
            result = wrapper.get_file_content(DeploymentPlatform.WINDOWS_X86, address, decoy_path)
            assert result.returncode == 0
            assert result.stdout.strip() == decoy_content
    finally:
        for address in windows_hosts:
            _unused = wrapper.windows_command_wrapper.remove_items(address, decoy_path)

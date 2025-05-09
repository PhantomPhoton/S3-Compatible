# S3 Compatible for Home Assistant

A Home Assistant custom integration to support uploading backups to S3 compatible endpoints. This is a slight modification of the official [AWS S3](https://www.home-assistant.io/integrations/aws_s3) integration.

## Installation

You can install this component in two ways: via [HACS](https://github.com/hacs/integration) or manually.

### Option A: Installing via HACS

1. Open HACS
2. Click the three dots in the upper right
3. Click on Custom repositories
4. Put `https://github.com/PhantomPhoton/S3-Compatible` as the repository
5. Select `Integration` as the Type
6. Click Add
7. On main HASC screen, select `S3 Compatible` and install
8. Restart Home Assistant

### Option B: Manual installation (custom_component)

TODO

## Component configuration

Once the component has been installed, you need to configure it using the web interface in order to make it work.

1. Go to "Settings->Devices & Services".
2. Click "+ Add Integration".
3. Search for "S3 Compatible"
4. Select the integration and **Follow setup workflow**
5. Once finished, it will show up as an available backup target

[![hacs_badge](https://img.shields.io/badge/HACS-Default-orange.svg)](https://github.com/hacs/integration)
[![GitHub release](https://img.shields.io/github/release/PhantomPhoton/S3-Compatible.svg)](https://GitHub.com/PhantomPhoton/S3-Compatible/releases/)
[![HA integration usage](https://img.shields.io/badge/dynamic/json?color=41BDF5&logo=home-assistant&label=integration%20usage&suffix=%20installs&cacheSeconds=15600&url=https://analytics.home-assistant.io/custom_integrations.json&query=$.s3_compatible.total)](https://analytics.home-assistant.io/custom_integrations.json)

# S3 Compatible for Home Assistant

A Home Assistant custom integration to support uploading backups to S3 compatible endpoints. This is a slight modification of the official [AWS S3](https://www.home-assistant.io/integrations/aws_s3) integration.

## Known Working Services

* [Amazon S3](https://aws.amazon.com/s3/)
* [MinIO](https://min.io)
* [MEGA S4](https://mega.io/objectstorage)
* [Scaleway Object Storage](https://www.scaleway.com/en/object-storage/)
* [Storj](https://www.storj.io/cloud-object-storage)
* [Cloudflare R2](https://www.cloudflare.com/developer-platform/products/r2/)
* [Backblaze](https://www.backblaze.com/cloud-storage)
* [IDrive® e2](https://www.idrive.com/s3-storage-e2/)
* [Hetzner Object Storage](https://www.hetzner.com/storage/object-storage/)
* [SeaweedFS](https://seaweedfs.com)

## Installation

You can install this component in two ways: via [HACS](https://github.com/hacs/integration) or manually.

### Option A: Installing via HACS

1. Open HACS
2. Search for `S3 Compatible`
3. Expand the `Available for download` section
4. Select `S3 Compatible`
5. Click `Download` in the lower right of the details page
6. Restart Home Assistant
7. [Setup a new backup target location](https://my.home-assistant.io/redirect/config_flow_start/?domain=s3_compatible)
8. Once finished, it will show up as an available backup target


### Option B: Manual installation (custom_component)

1. Copy the `custom_components/s3_compatible` directory to your custom_components directory
2. Restart Home Assistant
3. Go to "Settings->Devices & Services".
4. Click "+ Add Integration".
5. Search for "S3 Compatible"
6. Select the integration and **Follow setup workflow**
7. Once finished, it will show up as an available backup target

from os import getenv
import requests
from urllib.parse import urljoin
import logging
from sys import stdout
from shutil import rmtree
from pathlib import Path
import json


def get_imports_url():
    return urljoin(arr_url, 'api/v3/manualimport')


def trigger_manual_import_url():
    return urljoin(arr_url, 'api/v3/command')


def request_body_file_entry(import_item):
    # common attributes
    file_entry = {
        'path': import_item['path'],
        'folderName': import_item['folderName'],
        'quality': import_item['quality'],
        'languages': import_item['languages']
    }

    # arr-software-specific attributes
    if arr_software == 'sonarr':
        file_entry['seriesId'] = import_item['series']['id']
        file_entry['episodeIds'] = [episode['id'] for episode in import_item['episodes']]
    elif arr_software == 'radarr':
        file_entry['movieId'] = import_item['movie']['id']

    return file_entry


def sync_manual_imports():
    get_imports_response = requests.get(get_imports_url(),
                                        params={'folder': import_path,
                                                'filterExistingFiles': import_filter_existing_files},
                                        headers={'x-api-key': arr_api_key})
    try:
        assert get_imports_response.status_code == 200
    except AssertionError:
        logger.error(f"Error during manual import item request, server responded {get_imports_response.status_code}\n{get_imports_response.text}")

    import_items = get_imports_response.json()

    trigger_manual_import_request_body = {
        'name': 'ManualImport',
        'importMode': 'move',
        'files': []
    }

    for import_item in import_items:
        if len(import_item['rejections']) == 0:
            trigger_manual_import_request_body['files'].append(request_body_file_entry(import_item))
            logger.info(f"Added item for manual import: {import_item['folderName']}")
        else:
            logger.info(f"Rejected item {import_item['folderName']} for manual import for reason(s): " +
                        "; ".join([f"{import_rejection['reason']} ({import_rejection['type']})" for import_rejection in import_item['rejections']]))

            if delete_rejected_items:
                logger.info(f"Trying to delete rejected item in folder {import_item['folderName']}")
                item_file_path = Path(download_folder_prefix) / Path(import_item['path'])

                try:
                    assert item_file_path.is_file()
                except AssertionError:
                    logger.error(f"Could not find downloaded file at {item_file_path}")

                try:
                    item_file_path.unlink()
                except:
                    logger.error(f"Could not unlink downloaded file at {item_file_path}", exc_info=True)

                # parent path of item is empty
                if delete_rejected_item_folders and next(item_file_path.parent.iterdir(), None) is None:
                    rmtree(item_file_path.parent)

    if (import_file_count := len(trigger_manual_import_request_body['files'])) > 0:
        logger.info(f"Requesting manual import of {import_file_count} files")
        trigger_manual_import_response = requests.post(trigger_manual_import_url(),
                                               json=trigger_manual_import_request_body,
                                               headers={'x-api-key': arr_api_key})
        try:
            assert trigger_manual_import_response.status_code == 201
        except AssertionError:
            logger.error(f"Error during manual import request, server responded with {trigger_manual_import_response.status_code}\n{trigger_manual_import_response.text}")

        logger.info(f"Manual import request was successful, server responded with {trigger_manual_import_response.status_code}\n{trigger_manual_import_response.text}")


# region: config variables
log_level = getenv('LOG_LEVEL', 'INFO')
arr_software = getenv('ARR_SOFTWARE', 'radarr')
import_filter_existing_files = json.loads(getenv('IMPORT_FILTER_EXISTING_FILES', 'true').lower())
delete_rejected_items = json.loads(getenv('DELETE_REJECTED_ITEMS', 'false').lower())
delete_rejected_item_folders = json.loads(getenv('DELETE_REJECTED_ITEM_FOLDERS', 'true').lower())
download_folder_prefix = getenv('DOWNLOAD_FOLDER_PREFIX', '')

# mandatory variables
arr_url = getenv('ARR_URL', '')
arr_api_key = getenv('ARR_API_KEY', '')
import_path = getenv('IMPORT_PATH', '')
# endregion

logging.basicConfig(level=logging.getLevelName(log_level),
                    format='[%(asctime)s] - %(levelname)s - %(message)s',
                    handlers=[logging.StreamHandler(stdout)])
logger = logging.getLogger(__name__)

if __name__ == '__main__':
    # region: mandatory parameter assertions
    try:
        assert arr_software.lower() in ('sonarr', 'radarr')
    except AssertionError as err:
        logger.critical("Variable 'arr_software' not within allowed values: ['sonarr', 'radarr']")
        exit(1)

    for mandatory_param in ['arr_url', 'arr_api_key', 'import_path']:
        try:
            assert locals()[mandatory_param] != ''
        except AssertionError as err:
            logger.critical(f"Variable '{mandatory_param}' was empty or not supplied")
            exit(1)
    # endregion

    sync_manual_imports()

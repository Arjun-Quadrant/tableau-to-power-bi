import config
import requests
import time
import base64
import json
import os
import re
from msal import PublicClientApplication
from azure.storage.filedatalake import (
    DataLakeServiceClient,
    DataLakeDirectoryClient,
    FileSystemClient
)
from azure.identity import DefaultAzureCredential

CLIENT_ID = config.client_id
WORKSPACE_ID = config.workspace_id
TENANT_ID = config.tenant_id
METADATA_FOLDER_PATH = config.metadata_folder_path
METADATA_FILE_NAME = config.metadata_file_name
WORKSPACE_NAME = config.workspace_name
LAKEHOUSE_NAME = config.lakehouse_name
LAKEHOUSE_TABLE_NAME = config.lakehouse_table_name
LAKEHOUSE_METADATA_DIRECTORY = config.lakehouse_metadata_directory
SEMANTIC_MODEL_NAME = config.semantic_model_name
SEMANTIC_MODEL_FOLDER =  config.semantic_model_folder
REPORT_NAME = config.report_name
REPORT_FOLDER = config.report_folder
AUTH_USERNAME = config.auth_username
AUTH_PASSWORD = config.auth_password

def get_fabric_access_token():
    app_authority = f"https://login.microsoftonline.com/{TENANT_ID}/"
    app = PublicClientApplication(CLIENT_ID, authority=app_authority)
    fabric_scope = ["https://api.fabric.microsoft.com/.default"]
    result = app.acquire_token_by_username_password(AUTH_USERNAME, AUTH_PASSWORD, scopes=fabric_scope)
    return result["access_token"]

def get_sharepoint_access_token():
    app_authority = f"https://login.microsoftonline.com/{TENANT_ID}/"
    app = PublicClientApplication(CLIENT_ID, authority=app_authority)
    sharepoint_scope = [f"https://{TENANT_ID}.sharepoint.com/.default"]
    result = app.acquire_token_by_username_password(AUTH_USERNAME, AUTH_PASSWORD, scopes=sharepoint_scope)
    return result["access_token"]

def wait_for_resource_creation(post_url, post_headers, post_payload, poll_interval=10, max_attempts=50):
    # Make the initial POST request
    response = requests.post(url=post_url, headers=post_headers, json=post_payload)

    if response.status_code == 201:
        return response.json()
    
    if response.status_code != 202:
        raise Exception(f"Unexpected status code: {response.status_code}")
        
    # Extract the URL for polling from the Location header (or response body)
    status_url = response.headers.get('Location')

    if not status_url:
        raise Exception("No Location header found in the 202 response.")
    
    # Poll the status URL until the resource is created
    for attempt in range(max_attempts):
        time.sleep(poll_interval)
        status_response = requests.get(status_url, headers=post_headers)
        if status_response.json()["status"] == "Succeeded":
            response = requests.get(f"{status_url}/result", headers=post_headers)
            return response.json()
    raise Exception("Resource creation did not complete in time.")

def create_lakehouse(token):
    url = f"https://api.fabric.microsoft.com/v1/workspaces/{WORKSPACE_ID}/lakehouses"
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {token}"
    }
    lakehouse_payload = {
        "displayName": LAKEHOUSE_NAME,
        "description": "A lakehouse for storing metadata from Tableau"
    }
    response = wait_for_resource_creation(url, headers, lakehouse_payload)
    return response

def create_file_system_client(service_client: DataLakeServiceClient, file_system_name: str) -> FileSystemClient: 
    file_system_client = service_client.get_file_system_client(file_system = file_system_name)
    return file_system_client

def create_directory(file_system_client : FileSystemClient, directory_name) -> DataLakeDirectoryClient:
    directory_client = file_system_client.create_directory(f"{LAKEHOUSE_NAME}.Lakehouse/Files/{directory_name}")
    return directory_client

def list_directory_contents(file_system_client: FileSystemClient, directory_name: str):
    paths = file_system_client.get_paths(path=directory_name)
    for path in paths:
        print(path.name + '\n')

def upload_file_to_directory(directory_client: DataLakeDirectoryClient, file_path: str):
    file_client = directory_client.get_file_client(METADATA_FILE_NAME)
    with open(file=file_path, mode="rb") as data:
        file_client.upload_data(data, overwrite=True)

def upload_file_to_lakehouse():
    account_url = "https://onelake.dfs.fabric.microsoft.com"
    token_credential = DefaultAzureCredential()   
    service_client = DataLakeServiceClient(account_url, credential=token_credential)
    file_system_client = create_file_system_client(service_client, WORKSPACE_NAME)
    directory_client = create_directory(file_system_client, LAKEHOUSE_METADATA_DIRECTORY)
    upload_file_to_directory(directory_client, f"{METADATA_FOLDER_PATH}/{METADATA_FILE_NAME}")
    
def load_lakehouse_table(token, lakehouse_id):
    url = f"https://api.fabric.microsoft.com/v1/workspaces/{WORKSPACE_ID}/lakehouses/{lakehouse_id}/tables/{LAKEHOUSE_TABLE_NAME}/load"

    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {token}"
    }

    table_payload = {
        "relativePath": f"Files/{LAKEHOUSE_METADATA_DIRECTORY}/{METADATA_FILE_NAME}",
        "pathType": "File",
        "mode": "Overwrite",
        "recursive": False,
        "formatOptions": {
            "delimiter": ",",
            "format": "Csv",
            "header": True
        }
    }
    wait_for_resource_creation(url, headers, table_payload)

def encode_to_base_64(path):
     with open(path, 'rb') as binary_file:
        binary_file_data = binary_file.read()
        base64_encoded_data = base64.b64encode(binary_file_data)
        base64_output = base64_encoded_data.decode('utf-8')
        return base64_output
     
def switch_to_connection_reference(path, semantic_model_id, semantic_model_name, workspace_name):
    with open(path, 'r+') as file:
        content = file.read()
        file.truncate(0)
        json_data = json.loads(content)
        json_data["datasetReference"]["byPath"] = None
        json_data["datasetReference"]["byConnection"] = {
        "connectionString": f"Data Source=powerbi://api.powerbi.com/v1.0/myorg/{workspace_name};Initial Catalog={semantic_model_name};Integrated Security=ClaimsToken",
        "pbiServiceModelId": None,
        "pbiModelVirtualServerName": "sobe_wowvirtualserver",
        "pbiModelDatabaseName": f"{semantic_model_id}",
        "connectionType": "pbiServiceXmlaStyleLive",
        "name": "EntityDataSource"
        }
        file.seek(0)
        file.write(json.dumps(json_data))

def append_all_files(parts: list, pattern: re.Pattern[str], base_dir=".", dataset_id=None, dataset_name=None, workspace_name=None):
    for root, folders, files in os.walk(base_dir):
        for file in files:
            file_full_path = os.path.join(root, file)
            relative_path = os.path.relpath(file_full_path, base_dir)
            # Replace Windows backslashes with forward slashes
            relative_path = relative_path.replace("\\", "/")
            if pattern.search(relative_path):
                if "definition.pbir" in relative_path:
                    switch_to_connection_reference(relative_path, dataset_id, dataset_name, workspace_name=workspace_name)
                parts.append({
                "path": relative_path, 
                "payload": encode_to_base_64(relative_path),
                "payloadType": "InlineBase64"
                })

def create_dataset_payload():
    dataset_payload = {}
    dataset_payload["displayName"] = SEMANTIC_MODEL_NAME
    dataset_payload["description"] = "Data on Netflix movies"
    parts = []
    regexp = re.compile(r"definition/|definition.pbism|diagramLayout.json|.platform")
    append_all_files(parts, regexp)
    dataset_payload["definition"] = {"parts": []}
    dataset_payload["definition"]["parts"] = parts
    return dataset_payload

def create_report_payload(dataset_id, dataset_name, workspace_name):
    report_payload = {}
    report_payload["displayName"] = REPORT_NAME
    report_payload["description"] = "Report on Netflix movies"
    parts = []
    regexp = re.compile(r"CustomVisuals/|StaticResources/|definition.pbir|definition/|semanticModelDiagramLayout.json|mobileState.json")
    append_all_files(parts, regexp, dataset_id=dataset_id, dataset_name=dataset_name, workspace_name=workspace_name)
    report_payload["definition"] = {"parts": []}
    report_payload["definition"]["parts"] = parts
    return report_payload

def create_semantic_model(token):
    url = f"https://api.fabric.microsoft.com/v1/workspaces/{WORKSPACE_ID}/semanticModels"

    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {token}"
    }

    semantic_model_folder = SEMANTIC_MODEL_FOLDER
    os.chdir(semantic_model_folder)
    dataset_payload = create_dataset_payload()
    response = wait_for_resource_creation(url, headers, dataset_payload)
    return response

def get_connection_id_for_semantic_model(token, semantic_model_id):
    url = f"https://api.powerbi.com/v1.0/myorg/groups/{WORKSPACE_ID}/datasets/{semantic_model_id}/datasources"

    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {token}"
    }

    connections = requests.get(url, headers=headers)
    # If there is no data connection, that means that we have an empty report
    if (not connections.json()["value"]):
        return None, None
    connection_info = connections.json()["value"][0]
    return connection_info["datasourceId"], connection_info["gatewayId"]

def update_connection(token, connection_id, gateway_id):
    url = f"https://api.powerbi.com/v1.0/myorg/gateways/{gateway_id}/datasources/{connection_id}"

    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {token}"
    }

    token = get_sharepoint_access_token()

    payload = {
        "credentialDetails": {
            "credentialType": "OAuth2",
            "credentials": f"{{\"credentialData\":[{{\"name\":\"accessToken\", \"value\":\"{token}\"}}]}}",
            "encryptedConnection": "Encrypted",
            "encryptionAlgorithm": "None",
            "privacyLevel": "Organizational"
        }
    }
    requests.patch(url, headers=headers, json=payload)

def create_report(token, dataset_id, dataset_name):
    url = f"https://api.fabric.microsoft.com/v1/workspaces/{WORKSPACE_ID}/reports"

    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {token}"
    }

    report_folder = REPORT_FOLDER
    os.chdir(report_folder)
    report_payload = create_report_payload(dataset_id, dataset_name, WORKSPACE_NAME)
    requests.post(url, headers=headers, json=report_payload)

def refresh_data(semantic_model_id, token):
    url = f"https://api.powerbi.com/v1.0/myorg/datasets/{semantic_model_id}/refreshes"

    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {token}"
    }

    payload = {
        "notifyOption": "NoNotification"
    }

    requests.post(url, headers=headers, json=payload)
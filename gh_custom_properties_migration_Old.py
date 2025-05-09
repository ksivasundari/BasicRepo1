from dotenv import load_dotenv
import argparse
import os
import requests
import json
import time
import csv
from datetime import datetime


# GitHub API base URL
API_URL = "https://api.github.com"

# GitHub API base URLs
GH_SOURCE_BASE_API_URL = "https://api.github.com"
GH_TARGET_BASE_API_URL = "https://api.github.com"

def create_github_client(base_url, token, verify_ssl=True):
    session = requests.Session()
    session.headers.update({
        'Authorization': f'token {token}',
        'Accept': 'application/vnd.github.v3+json'
    })
    session.verify = verify_ssl
    session.base_url = base_url
    return session

def fetch_labels(session, repo_fullname):
    url = f"{session.base_url}/repos/{repo_fullname}/labels"
    response = session.get(url)
    response.raise_for_status()
    labels=response.json()
    print(f"Labels in {repo_fullname}: {labels}")  # Debugging line
    return response.json()

def create_label(session, repo_fullname, label):
    url = f"{session.base_url}/repos/{repo_fullname}/labels"
    data = {
        'name': label['name'],
        'color': label['color'],
        'description': label.get('description', '')
    }
    response = session.post(url, json=data)
    if response.status_code == 422:
        print(f"Label '{label['name']}' already exists in {repo_fullname}.")
    else:
        response.raise_for_status()
        print(f"Created label '{label['name']}' in {repo_fullname}.")

def fetch_milestones(session, repo_fullname):
    url = f"{session.base_url}/repos/{repo_fullname}/milestones?state=all"
    response = session.get(url)
    response.raise_for_status()
    milestone = response.json()
    print(f"Milestones in {repo_fullname}: {milestone}")  # Debugging line
    return response.json()

def create_milestone(session, repo_fullname, milestone):
    url = f"{session.base_url}/repos/{repo_fullname}/milestones"
    data = {
        'title': milestone['title'],
        'state': milestone['state'],
        'description': milestone.get('description', ''),
        'due_on': milestone.get('due_on', None)
    }
    response = session.post(url, json=data)
    if response.status_code == 422:
        print(f"Milestone '{milestone['title']}' already exists in {repo_fullname}.")
    else:
        response.raise_for_status()
        print(f"Created milestone '{milestone['title']}' in {repo_fullname}.")

def fetch_custom_properties(org_name, repo_name):
    try:
        url = f"{API_URL}/repos/{org_name}/{repo_name}/properties/values"
        headers = {
            'Authorization': f'token {os.getenv("GITHUB_TOKEN")}',
            'Accept': 'application/vnd.github.v3+json'
        }
        response = requests.get(url, headers=headers, verify=os.getenv('CERT_PATH', False))
        if response.status_code == 200:
            return response.json()
        else:
            print(f"[ERROR] Failed to fetch properties for {org_name}/{repo_name}")
            return {}
    except Exception as e:
        print(f"[ERROR] Exception fetching properties: {str(e)}")
        return {}
    
def migrate_labels_and_milestones(source_session, target_session, source_repo_fullname, target_repo_fullname):
    try:
        print(f"\nMigrating from {source_repo_fullname} to {target_repo_fullname}")

        labels = fetch_labels(source_session, source_repo_fullname)
        for label in labels:
            create_label(target_session, target_repo_fullname, label)

        milestones = fetch_milestones(source_session, source_repo_fullname)
        for milestone in milestones:
            create_milestone(target_session, target_repo_fullname, milestone)

        return True, "Success"
    except Exception as e:
        print(f"Error migrating {source_repo_fullname} -> {target_repo_fullname}: {str(e)}")
        return False, str(e)

def extract_org_and_repo(full_repo_path):
    """
    Extracts the organization name and repository name from the full repository path.
    Example: 'org_name/repo_name' -> ('org_name', 'repo_name')
    """
    try:
        org_name, repo_name = full_repo_path.split('/')
        return org_name, repo_name
    except ValueError:
        raise ValueError(f"Invalid repository path format: {full_repo_path}")
        
def custom_setting_add(full_repo_path, custom_properties):
    try:
        # Extract org name and repo name
        org_name, repo_name = extract_org_and_repo(full_repo_path)
        
        # URL to assign repository custom properties
        custom_property_url = f"{API_URL}/repos/{org_name}/{repo_name}/properties/values"
        
        # Structure the custom properties as required by GitHub API
        payload = {
            "property_values": [
                {"property_name": k, "value": v}
                for k, v in custom_properties.items()
            ]
        }

        # Make the PATCH request to update custom properties
        response = requests.patch(
            custom_property_url,
            headers={
                'Authorization': f'token {os.getenv("GITHUB_TOKEN")}',
                'Accept': 'application/vnd.github.v3+json'
            },
            json=payload,
            verify=os.getenv('CERT_PATH', False)
        )
        
        if response.status_code == 204:
            print(f"[SUCCESS] Set custom property for repository '{full_repo_path}'")
        else:
            print(f"[ERROR] Failed to set custom property - status code: {response.status_code}")
            try:
                print(response.json())
            except Exception:
                print("[ERROR] Failed to parse error response as JSON.")
    except Exception as e:
        print(f"[ERROR] Error adding custom properties for '{full_repo_path}': {str(e)}")



def migrate_custom_metadata(source_repo, target_repo, source_token, target_token):
    file_path = '.github/custom-metadata.json'

    # Get file content from source
    source_url = f"https://api.github.com/repos/{source_repo}/contents/{file_path}"
    headers = {"Authorization": f"token {source_token}"}
    r = requests.get(source_url, headers=headers)
    
    if r.status_code != 200:
        print(f"⚠️ Metadata file not found in {source_repo}")
        return
    
    file_data = r.json()
    content = file_data['content']
    sha = file_data['sha']
    decoded_content = base64.b64decode(content).decode()

    # Push file to target repo
    target_url = f"https://api.github.com/repos/{target_repo}/contents/{file_path}"
    headers = {"Authorization": f"token {target_token}"}
    data = {
        "message": "Add custom metadata file",
        "content": content,
        "branch": "main"
    }
    r = requests.put(target_url, headers=headers, json=data)
    
    if r.status_code in [200, 201]:
        print(f"✅ Custom metadata migrated from {source_repo} to {target_repo}")
    else:
        print(f"❌ Failed to upload metadata to {target_repo}: {r.status_code}, {r.text}")

def log_migration(output_file, timestamp, source_repo, target_repo, status, error):
    with open(output_file, 'a', newline='') as csvfile:
        writer = csv.writer(csvfile)
        writer.writerow([timestamp, source_repo, target_repo, status, error])

def main():
    parser = argparse.ArgumentParser(description="Migrate GitHub repo labels and milestones across organizations.")
    parser.add_argument('--input_file', required=True, help='Input file with repo mappings (source::target)')
    parser.add_argument('--source_token_env', required=True, help='Env var name for source GitHub token')
    parser.add_argument('--target_token_env', required=True, help='Env var name for target GitHub token')
    parser.add_argument('--output_dir', required=True, help='Directory for logs')
    parser.add_argument('--source_base_url', default='https://api.github.com', help='Source GitHub API base URL')
    parser.add_argument('--target_base_url', default='https://api.github.com', help='Target GitHub API base URL')
    parser.add_argument('--verify_source', type=bool, default=True)
    parser.add_argument('--verify_target', type=bool, default=True)
    
    args = parser.parse_args()

    os.makedirs(args.output_dir, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_file = os.path.join(args.output_dir, f"migration_log_{timestamp}.csv")

    with open(log_file, 'w', newline='') as csvfile:
        writer = csv.writer(csvfile)
        writer.writerow(["Timestamp", "Source Repo", "Target Repo", "Status", "Error"])

    source_token = os.getenv(args.source_token_env)
    target_token = os.getenv(args.target_token_env)

    if not source_token or not target_token:
        print("Error: Source or target token not found in environment variables.")
        return      
    print(f"Source Token: {source_token}")
    print(f"Source Base URL: {args.source_base_url}")

    print(f"Target Token: {target_token}")
    print(f"Target Base URL: {args.target_base_url}")

    print(f"Verify Source SSL: {args.verify_source}")
    print(f"Verify Target SSL: {args.verify_target}")           
    source_client = create_github_client(args.source_base_url, source_token, args.verify_source)
    target_client = create_github_client(args.target_base_url, target_token, args.verify_target)

    with open(args.input_file, 'r') as f:
        for line in f:
            if '::' not in line:
                continue
            source_repo_fullname, target_repo_fullname = line.strip().split('::')
            success, error = migrate_labels_and_milestones(source_client, target_client, source_repo_fullname, target_repo_fullname)
            status = "Success" if success else "Failed"
            log_migration(log_file, timestamp, source_repo_fullname, target_repo_fullname, status, error)

if __name__ == '__main__':
    load_dotenv()
    main()

def validate_migration(source_session, target_session, source_repo_fullname, target_repo_fullname):
    source_labels = fetch_labels(source_session, source_repo_fullname)
    target_labels = fetch_labels(target_session, target_repo_fullname)

    source_milestones = fetch_milestones(source_session, source_repo_fullname)
    target_milestones = fetch_milestones(target_session, target_repo_fullname)

    # Validate labels
    for label in source_labels:
        if label['name'] not in [t_label['name'] for t_label in target_labels]:
            print(f"Label '{label['name']}' not found in target repository.")

    # Validate milestones
    for milestone in source_milestones:
        if milestone['title'] not in [t_milestone['title'] for t_milestone in target_milestones]:
            print(f"Milestone '{milestone['title']}' not found in target repository.")    

from dotenv import load_dotenv
import requests
import json
import os
import logging
import datetime
import argparse

API_URL = "https://api.github.com"
GITHUB_TOKEN = None
CERT_PATH = None

headers = {}

def log_and_print(message, level='info'):
    timestamp = datetime.datetime.now().strftime('%d%b%Y_%H%M%S')
    if level == 'error':
        logging.error(message)
        print(f"\033[31m{timestamp}: {message}\033[0m")
    elif level == 'success':
        logging.info(message)
        print(f"\033[32m{timestamp}: {message}\033[0m")
    else:
        logging.info(message)
        print(f"{timestamp}: {message}")

def extract_org_and_repo(repo_str):
    if '/' not in repo_str:
        raise ValueError(f"Invalid format '{repo_str}'. Must be 'org/repo'")
    return repo_str.split('/')

def load_repo_pairs(file_path):
    repo_pairs = []
    with open(file_path, 'r') as f:
        for line in f:
            parts = line.strip().split('::')
            if len(parts) == 2:
                repo_pairs.append((parts[0].strip(), parts[1].strip()))
    return repo_pairs

def fetch_custom_properties(org, repo):
    try:
        url = f"{API_URL}/repos/{org}/{repo}/properties/values"
        response = requests.get(url, headers=headers, verify=CERT_PATH if CERT_PATH else False)
        if response.status_code == 200:
            return response.json()
        else:
            print(f"Failed to fetch properties from {org}/{repo} - {response.status_code}", "error")
            return {}
    except Exception as e:
        print(f"Exception while fetching properties: {str(e)}", "error")
        return {}

def apply_custom_properties(org, repo, properties_data):
    try:
        if not properties_data.get('properties'):
            print(f"No properties to apply to {org}/{repo}", "info")
            return
        url = f"{API_URL}/repos/{org}/{repo}/properties/values"
        payload = {"properties": properties_data['properties']}
        response = requests.patch(url, headers=headers, json=payload, verify=CERT_PATH if CERT_PATH else False)
        if response.status_code == 204:
            print(f"[SUCCESS] Applied custom properties to {org}/{repo}", "success")
        else:
            print(f"[ERROR] Failed to apply properties to {org}/{repo} - {response.status_code}", "error")
            print(response.json(), "error")
    except Exception as e:
        print(f"Exception while applying properties: {str(e)}", "error")

def main():
    parser = argparse.ArgumentParser(description="Migrate GitHub custom properties from one org/repo to another.")
    parser.add_argument('-i', '--input_file', required=True, help='Path to input file containing source::target repo pairs')
    parser.add_argument('-t', '--token_env', default='GITHUB_TOKEN', help='Environment variable containing GitHub token')
    parser.add_argument('-c', '--cert', help='Optional certificate path for HTTPS verification')

    args = parser.parse_args()

    global GITHUB_TOKEN, CERT_PATH, headers
    GITHUB_TOKEN = os.getenv(args.token_env)
    if not GITHUB_TOKEN:
        raise ValueError(f"GitHub token not found in environment variable {args.token_env}")
    
    CERT_PATH = args.cert
    headers = {
        "Authorization": f"token {GITHUB_TOKEN}",
        "Accept": "application/vnd.github.v3+json"
    }

    repo_pairs = load_repo_pairs(args.input_file)
    log_and_print(f"Total repo pairs to process: {len(repo_pairs)}")

    for index, (source_repo, target_repo) in enumerate(repo_pairs, 1):
        log_and_print(f"--- [{index}] Migrating from {source_repo} -> {target_repo} ---")
        try:
            src_org, src_repo = extract_org_and_repo(source_repo)
            tgt_org, tgt_repo = extract_org_and_repo(target_repo)

            properties_data = fetch_custom_properties(src_org, src_repo)
            if properties_data:
                apply_custom_properties(tgt_org, tgt_repo, properties_data)
        except Exception as e:
            log_and_print(f"Error processing {source_repo} -> {target_repo}: {str(e)}", "error")

    log_and_print("✅ Migration complete.")

if __name__ == "__main__":
    load_dotenv()
    logging.basicConfig(filename='migration.log', level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
    logging.getLogger().addHandler(logging.StreamHandler()) 
    main()
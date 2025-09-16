import json
import os
import sys
from elasticsearch import Elasticsearch
from elasticsearch.helpers import bulk
import requests
import time


def read_mapping_file(filename="mapping.json"):
    """Read the Elasticsearch mapping from a JSON file"""
    try:
        with open(filename, 'r') as f:
            mapping_data = json.load(f)
        print(f"✓ Successfully read mapping from {filename}")
        return mapping_data
    except FileNotFoundError:
        print(f"✗ Error: {filename} not found in current directory")
        sys.exit(1)
    except json.JSONDecodeError as e:
        print(f"✗ Error: Invalid JSON in {filename}: {e}")
        sys.exit(1)


def connect_to_elasticsearch(host, api_key):
    """Create and return Elasticsearch client"""
    try:
        es = Elasticsearch(
            hosts=[host],
            api_key=api_key,
            request_timeout=60
        )

        # Test the connection
        if es.ping():
            print(f"✓ Successfully connected to Elasticsearch at {host}")
            return es
        else:
            print("✗ Failed to connect to Elasticsearch")
            return None
    except Exception as e:
        print(f"✗ Error connecting to Elasticsearch: {e}")
        return None


def create_index(es, index_name, mapping):
    """Create Elasticsearch index with the provided mapping"""
    try:
        # Check if index exists and delete it
        if es.indices.exists(index=index_name):
            print(f"⚠ Index '{index_name}' already exists. Deleting it first...")
            es.indices.delete(index=index_name)
            print(f"✓ Successfully deleted existing index '{index_name}'")

        # Create the index with mapping
        es.indices.create(index=index_name, body=mapping)
        print(f"✓ Successfully created index '{index_name}' with mapping")
        return True

    except Exception as e:
        print(f"✗ Failed to create index: {e}")
        return False


def parse_ndjson_for_bulk(filename):
    """Parse NDJSON file and yield documents for bulk indexing"""
    try:
        with open(filename, 'r') as f:
            lines = f.readlines()

        documents = []
        i = 0
        while i < len(lines):
            # Skip empty lines
            if not lines[i].strip():
                i += 1
                continue

            try:
                # Parse index action line
                index_action = json.loads(lines[i].strip())
                if i + 1 < len(lines):
                    # Parse document data line
                    doc_data = json.loads(lines[i + 1].strip())

                    # Extract index and id from index action
                    index_info = index_action.get('index', {})
                    doc = {
                        '_index': index_info.get('_index'),
                        '_id': index_info.get('_id'),
                        '_source': doc_data
                    }
                    documents.append(doc)
                    i += 2  # Skip both lines
                else:
                    print(f"⚠ Warning: Missing document data for index action at line {i + 1}")
                    i += 1
            except json.JSONDecodeError as e:
                print(f"⚠ Warning: Invalid JSON at line {i + 1}: {e}")
                i += 1

        print(f"✓ Successfully parsed {len(documents)} documents from {filename}")
        return documents

    except FileNotFoundError:
        print(f"✗ Error: {filename} not found in current directory")
        return None
    except Exception as e:
        print(f"✗ Error parsing NDJSON file: {e}")
        return None


def bulk_index_documents(es, filename="bulk_index.ndjson"):
    """Read NDJSON file and bulk index documents to Elasticsearch"""
    # Parse the NDJSON file
    documents = parse_ndjson_for_bulk(filename)
    if documents is None:
        return False

    if not documents:
        print(f"✗ No documents found in {filename}")
        return False

    try:
        # Use elasticsearch.helpers.bulk for efficient bulk indexing
        success_count, failed_items = bulk(
            es,
            documents,
            index=None,  # Index is specified in each document
            chunk_size=1000
        )

        if failed_items:
            print(f"⚠ Bulk indexing completed with {len(failed_items)} failures:")
            for failure in failed_items[:5]:  # Show first 5 failures
                print(f"  - {failure}")
            if len(failed_items) > 5:
                print(f"  ... and {len(failed_items) - 5} more failures")

        print(f"✓ Successfully indexed {success_count} documents")
        return True

    except Exception as e:
        print(f"✗ Error during bulk indexing: {e}")
        return False


def main():
    """Main function to control the script flow"""
    print("🚀 Starting Elasticsearch index creation and data loading...")

    # Get environment variables
    es_host = os.getenv('ES_HOST')
    api_key = os.getenv('API_KEY')

    if not es_host:
        print("✗ Error: ES_HOST environment variable not set")
        print("   Example: export ES_HOST='https://localhost:9200'")
        sys.exit(1)

    if not api_key:
        print("✗ Error: API_KEY environment variable not set")
        print("   Example: export API_KEY='your-api-key-here'")
        sys.exit(1)

    print(f"📡 Connecting to Elasticsearch at: {es_host}")

    # Step 1: Connect to Elasticsearch
    es = connect_to_elasticsearch(es_host, api_key)
    if not es:
        sys.exit(1)

    # Step 2: Read mapping file
    ubi_queries_mapping = read_mapping_file("elastic_data/ubi_events-mappings.json")

    ubi_queries_mapping = read_mapping_file("elastic_data/ubi_events-mappings.json")

    # Step 3: Create index with mapping

    if not create_index(es, "ubi_events", ubi_queries_mapping):
        sys.exit(1)

    if not create_index(es, "ubi_queries", ubi_queries_mapping):
        sys.exit(1)

    # Step 4: Bulk index documents
    if not bulk_index_documents(es, "elastic_data/bulk_index.ndjson"):
        sys.exit(1)

    print("🎉 Script completed successfully!")

    return


if __name__ == "__main__":
    start_time = time.time()
    main()
    print("Total time: %s seconds " % (time.time() - start_time))
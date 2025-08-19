import pandas as pd
from elasticsearch import Elasticsearch
import json
from typing import Dict, List, Tuple
import logging
import os

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def fetch_ubi_data(es_client: Elasticsearch, queries_index: str, events_index: str,
                   size: int = 10000) -> Tuple[List[Dict], List[Dict]]:
    """
    Fetch UBI queries and events data from Elasticsearch indices.

    Args:
        es_client: Elasticsearch client
        queries_index: Name of the UBI queries index
        events_index: Name of the UBI events index
        size: Maximum number of documents to fetch

    Returns:
        Tuple of (queries_data, events_data)
    """
    logger.info(f"Fetching data from {queries_index} and {events_index}")

    # Fetch queries
    queries_response = es_client.search(
        index=queries_index,
        body={
            "query": {"match_all": {}},
            "size": size
        }
    )
    queries_data = [hit['_source'] for hit in queries_response['hits']['hits']]
    logger.info(f"Fetched {len(queries_data)} queries")

    # Fetch events (only click events for now)
    events_response = es_client.search(
        index=events_index,
        body={
            "query": {
                "term": {"message_type.keyword": "CLICK_THROUGH"}
            },
            "size": size
        }
    )
    events_data = [hit['_source'] for hit in events_response['hits']['hits']]
    logger.info(f"Fetched {len(events_data)} click events")

    return queries_data, events_data


def calculate_relevance_grade(document_id: str, clicks_data: Dict,
                              query_response_ids: List[str], all_queries_data: List[Dict] = None,
                              all_events_data: List[Dict] = None) -> float:
    """
    Calculate COEC (Click Over Expected Clicks) relevance score for a document.

    Args:
        document_id: ID of the document
        clicks_data: Dictionary of clicked documents with their positions for current query
        query_response_ids: List of document IDs shown in search results (ordered by position)
        all_queries_data: All queries data for calculating position CTR averages
        all_events_data: All events data for calculating position CTR averages

    Returns:
        COEC relevance score (continuous value, typically 0.0 to 5.0+)
    """

    # If no global data provided, fall back to simple position-based grading
    if all_queries_data is None or all_events_data is None:
        logger.warning("No global data provided, falling back to position-based grading")
        # Simple fallback logic
        if document_id in clicks_data:
            position = clicks_data[document_id]['position']
            if position > 3:
                return 4.0
            elif position >= 1 and position <= 3:
                return 3.0
        if document_id in query_response_ids:
            position = query_response_ids.index(document_id) + 1
            if position <= 5:
                return 2.0
            elif position >= 6 and position <= 10:
                return 1.0
        return 0.0

    # Calculate rank-aggregated click-through rates
    position_ctr_averages = {}
    position_impression_counts = {}
    position_click_counts = {}

    # Initialize counters
    for pos in range(1, 11):  # Positions 1-10
        position_impression_counts[pos] = 0
        position_click_counts[pos] = 0

    # Count impressions (every document shown contributes)
    for query in all_queries_data:
        for i, doc_id in enumerate(query['query_response_object_ids'][:10]):  # Top 10 positions
            position = i + 1
            position_impression_counts[position] += 1

    # Count clicks by position
    for event in all_events_data:
        if event.get('action_name') == 'click':
            position = event['event_attributes']['object']['position']['ordinal']
            if position <= 10:
                position_click_counts[position] += 1

    # Calculate average CTR per position
    for pos in range(1, 11):
        if position_impression_counts[pos] > 0:
            position_ctr_averages[pos] = position_click_counts[pos] / position_impression_counts[pos]
        else:
            position_ctr_averages[pos] = 0.0

    # Calculate expected clicks for this specific document
    expected_clicks = 0.0

    # Count how many times this document appeared at each position for any query
    for query in all_queries_data:
        if document_id in query['query_response_object_ids']:
            position = query['query_response_object_ids'].index(document_id) + 1
            if position <= 10:
                expected_clicks += position_ctr_averages[position]

    # Count total actual clicks for this document across all queries
    actual_clicks = 0
    for event in all_events_data:
        if (event.get('action_name') == 'click' and
                event['event_attributes']['object']['object_id'] == document_id):
            actual_clicks += 1

    # Calculate COEC score
    if expected_clicks > 0:
        coec_score = actual_clicks / expected_clicks
    else:
        coec_score = 0.0

    logger.debug(
        f"Document {document_id}: {actual_clicks} clicks / {expected_clicks:.3f} expected = {coec_score:.3f} COEC")

    return coec_score


def process_ubi_data(queries_data: List[Dict], events_data: List[Dict]) -> pd.DataFrame:
    """
    Process UBI data and generate judgment list.

    Args:
        queries_data: List of query documents from UBI queries index
        events_data: List of event documents from UBI events index

    Returns:
        DataFrame with judgment list (qid, docid, grade, keywords)
    """
    logger.info("Processing UBI data to generate judgment list")

    # Group events by query_id
    clicks_by_query = {}
    for event in events_data:
        query_id = event['query_id']
        if query_id not in clicks_by_query:
            clicks_by_query[query_id] = {}

        # Extract clicked document info
        object_id = event['event_attributes']['object']['object_id']
        position = event['event_attributes']['object']['position']['ordinal']

        clicks_by_query[query_id][object_id] = {
            'position': position,
            'timestamp': event['timestamp']
        }

    judgment_list = []

    # Process each query
    for query in queries_data:
        query_id = query['query_id']
        user_query = query['user_query']
        document_ids = query['query_response_object_ids']

        # Get clicks for this query
        query_clicks = clicks_by_query.get(query_id, {})

        # Generate judgment for each document shown
        for doc_id in document_ids:
            grade = calculate_relevance_grade(doc_id, query_clicks, document_ids,
                                              queries_data, events_data)

            judgment_list.append({
                'qid': query_id,
                'docid': doc_id,
                'grade': grade,
                'query': user_query
            })

    df = pd.DataFrame(judgment_list)
    logger.info(f"Generated {len(df)} judgment entries for {df['qid'].nunique()} unique queries")

    return df


def generate_judgment_statistics(df: pd.DataFrame) -> Dict:
    """Generate statistics about the judgment list."""
    stats = {
        'total_judgments': len(df),
        'unique_queries': df['qid'].nunique(),
        'unique_documents': df['docid'].nunique(),
        'grade_distribution': df['grade'].value_counts().to_dict(),
        'avg_judgments_per_query': len(df) / df['qid'].nunique() if df['qid'].nunique() > 0 else 0,
        'queries_with_clicks': len(df[df['grade'] > 1]['qid'].unique()),
        'click_through_rate': len(df[df['grade'] > 1]) / len(df) if len(df) > 0 else 0
    }
    return stats


def main():
    """Main function to generate judgment list from UBI data."""

    # Configuration
    queries_index = "ubi_queries1"  # Update with your queries index name
    events_index = "ubi_events2"  # Update with your events index name
    output_file = "judgment_list.csv"
    api_key = os.getenv("ELASTICSEARCH_API_KEY")
    es_host = os.getenv("ELASTICSEARCH_HOST")

    print(es_host)
    try:
        # Initialize Elasticsearch client
        es = Elasticsearch(hosts=es_host, api_key=api_key)

        # Fetch UBI data
        queries_data, events_data = fetch_ubi_data(es, queries_index, events_index)

        # Generate judgment list
        judgment_df = process_ubi_data(queries_data, events_data)

        # Generate statistics
        stats = generate_judgment_statistics(judgment_df)
        logger.info(f"Judgment List Statistics: {json.dumps(stats, indent=2)}")

        # Save to CSV
        judgment_df.to_csv(output_file, index=False)
        logger.info(f"Judgment list saved to {output_file}")

        # Display sample
        logger.info("Sample judgment entries:")
        print(judgment_df.head(10))

        return judgment_df

    except Exception as e:
        logger.error(f"Error generating judgment list: {str(e)}")
        raise


if __name__ == "__main__":
    judgment_df = main()


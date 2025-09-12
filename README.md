# Elastic Learning-to-Rank Judgment List Generator
A project for generating relevance judgments from Elasticsearch User Behavior Insights (UBI) data using the COEC (Click Over Expected Clicks) algorithm. This system transforms implicit user feedback into explicit relevance scores suitable for training Learning-to-Rank models.

## Overview
This repository processes user search queries and click interactions stored in Elasticsearch UBI indices to produce judgment lists that quantify document relevance on a continuous scale. The system addresses position bias in click-through data by implementing the COEC algorithm, which normalizes click rates based on expected click-through rates for each search result position.

## Features
- COEC Algorithm Implementation: Calculates position-bias-corrected relevance scores 
- Elasticsearch Integration: Fetches data from UBI queries and events indices
- Statistical Analysis: Generates comprehensive metrics about judgment quality judgement_list-generator.py:208-219
- CSV Output: Produces standard LTR-compatible judgment files judgement_list-generator.py:247-249

## Requirements
Install dependencies from requirements.txt:
```
pip install pandas elasticsearch
```

## Configuration
Set the following environment variables:

```
ELASTICSEARCH_API_KEY: Your Elasticsearch API key
ELASTICSEARCH_HOST: Your Elasticsearch host URL
```


### Usage
Run the judgment list generator:

```
python judgement_list-generator.py
```

The script will:

1. Connect to Elasticsearch and fetch UBI data
2. Process queries and events to calculate COEC scores
3. Generate a CSV file with relevance judgments
4. Output statistical analysis of the results

## Data Structure

### Input Requirements

The system expects two Elasticsearch indices:

- Queries Index (ubi_queries): Contains search queries with result sets
- Events Index (ubi_events): Contains user click events with position information 
### Output Format
The generated judgment_list.csv contains: j

| Field | Description                  |  
|-------|------------------------------|
| qid   | Query identifier             |
| docid | Document identifier          | 
| grade | COEC relevance score (float) | 
| query | Query text                   |

### Algorithm Details
The COEC algorithm implementation:

1. Calculates position-based click-through rates across all historical data 
2. Computes expected clicks for each document based on its appearance positions 
3. Counts actual clicks received by the document 
4. Generates the COEC score as actual_clicks / expected_clicks
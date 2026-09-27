"""Uploads quiz and discussion records to Qdrant."""
import pandas as pd
from qdrant_client import QdrantClient

from qdrant_client.models import (
    FieldCondition,
    Filter,
    MatchValue,
    PayloadSchemaType,
    PointStruct,
)

from src.qdrant_common import (
    COLLECTION_NAME,
    MODEL_NAME,
    VECTOR_DIMENSIONS,
    clean_payload_value,
    create_client,
    create_point_id,
    parse_serialized_value,
)
from src.database_io import load_database, load_embeddings

UPLOAD_BATCH_SIZE = 100

DATABASE_CONTENT_TYPES = {
    "caption_database": "caption",
    "slide_database": "slide",
    "frame_database": "frame",
    "quiz_database": "quiz",
    "discussion_database": "discussion",
}

def prepare_payload(row:dict,
                    content_type:str,
                    embedding_record:dict)->dict:

    serialized_fields={
        "options",
        'concept_tags',
        'assessment_location',
        'topic',
        'chunk_ids',
        'timestamps',}

    payload={}

    for key, value in row.items():
        if key in serialized_fields:
            value = parse_serialized_value(value)

        payload[key] = clean_payload_value(value)

    if content_type=="quiz":
        linked_chunk_ids = parse_serialized_value(row.get("assessment_location"))
    else:
        linked_chunk_ids = parse_serialized_value(row.get("chunk_ids"))


    payload["linked_chunk_ids"] = clean_payload_value(linked_chunk_ids)
    payload['content_type'] = content_type
    payload['embedding_model'] = embedding_record['embedding_model']
    payload['embedding_dimensions'] = embedding_record['embedding_dimensions']

    return payload

def build_points(database_name:str,
                 content_type:str,)->list[PointStruct]:

    database_df = load_database(database_name)
    embedding_records = load_embeddings(database_name,  expected_count=len(database_df))
    
    database_rows = {
        str(row['record_id']):row
        for row in database_df.to_dict(orient='records')
    }

    embeddng_by_id ={
        str(record['record_id']):record
        for record in embedding_records
    }

    if set(database_rows.keys()) != set(embeddng_by_id.keys()):

        missing_embeddings = sorted(
            set(database_rows) - set(embeddng_by_id)
        )

        missing_database_rows = sorted(
            set(embeddng_by_id) - set(database_rows))

        raise ValueError(
            "Database/embedding ID mismacth."
            f"missing embeddings: {missing_embeddings[:10]}; "
            f"missing database rows: {missing_database_rows[:10]}"
        )

    points=[]

    for record_id,row in database_rows.items():
        embedding_record = embeddng_by_id[record_id]
        vector = embedding_record['embedding']

        if (embedding_record['embedding_model'] != MODEL_NAME):
            raise ValueError(f"{record_id} has wrong embedding model: {embedding_record['embedding_model']}")

        if len(vector) != VECTOR_DIMENSIONS:
            raise ValueError(f"{record_id} has wrong embedding dimensions: {len(vector)}, expected {VECTOR_DIMENSIONS}")

        payload = prepare_payload(row=row,
                                  content_type=content_type,
                                  embedding_record=embedding_record)

        points.append(PointStruct(
            id=create_point_id(record_id),
            vector=vector,
            payload=payload,
        ))
        
    return points

def upload_points(
        client:QdrantClient,
        points: list[PointStruct],
        content_type:str,)->None:

    for batch_start in range(0, len(points), UPLOAD_BATCH_SIZE):
        batch = points[batch_start:batch_start+UPLOAD_BATCH_SIZE]

        client.upsert(
            collection_name=COLLECTION_NAME,
            points=batch,
            wait=True,
        )

        uploaded = min(batch_start+ len(batch), len(points))

        print(f"{content_type} uploaded: {uploaded}/{len(points)}")

def ensure_content_type_index(
    client: QdrantClient,) -> None:
    """Ensure the content_type keyword index exists."""

    collection_info = client.get_collection(
        COLLECTION_NAME
    )

    if "content_type" in collection_info.payload_schema:
        print("content_type payload index already exists")
        return

    client.create_payload_index(
        collection_name=COLLECTION_NAME,
        field_name="content_type",
        field_schema=PayloadSchemaType.KEYWORD,
        wait=True,
    )

    print("created content_type keyword index")


def count_content_types(client:QdrantClient,
                        content_type:str)->int:

    result = client.count(
        collection_name=COLLECTION_NAME,
        count_filter=Filter(
            must=[
                FieldCondition(
                    key="content_type",
                    match=MatchValue(value=content_type),
                )
            ]
            ),
            exact=True,
        )
    return result.count


def main()->None:

    client = create_client()

    ensure_content_type_index(client)

    collection_info = client.get_collection(COLLECTION_NAME)

    vector_config = collection_info.config.params.vectors

    if vector_config.size != VECTOR_DIMENSIONS:
        raise ValueError(f"Wrong vector size: {vector_config.size}, expected {VECTOR_DIMENSIONS}")


    expected_counts = {}
    all_record_ids=[]

    for database_name,content_type in DATABASE_CONTENT_TYPES.items():

        database_df = load_database(database_name)
        expected_counts[content_type] = len(database_df)

        all_record_ids.extend(database_df['record_id'].astype(str).tolist())


    record_id_series = pd.Series(all_record_ids)
    duplicate_ids= sorted(record_id_series[record_id_series.duplicated()].unique())

    if duplicate_ids:
        raise ValueError(f"duplicate record_ids in qdrant: {duplicate_ids[:10]}")

    expected_final_count = sum(expected_counts.values())

    current_count = {
        content_type:count_content_types(client=client,content_type=content_type)   
        for content_type in expected_counts
    }


    before_count = client.count(
        collection_name=COLLECTION_NAME,
        exact=True,
    ).count


    print(f"collection name: {COLLECTION_NAME}")
    print('points before upload:',before_count)
    print('current content counts:',current_count)
    print('expected final content counts:',expected_counts)
    print('expected final count:',expected_final_count)

    for content_type in ('caption','slide','frame'):

        if ( current_count[content_type] != expected_counts[content_type]):
            raise ValueError(f"{content_type} content count mismatch:"
                              f"current {current_count[content_type]} != database contains {expected_counts[content_type]}")

        
    for content_type in ('quiz','discussion'):
        if ( current_count[content_type] > expected_counts[content_type]):

            raise ValueError(f"qdrant contains more {content_type} points than database contains:")

    known_curr_total = sum(current_count.values())

    if before_count != known_curr_total:
        raise ValueError(f"the collection contains points with missing or unexpected content types:")

    quiz_points = build_points(database_name="quiz_database",
                               content_type="quiz")

    discussion_points = build_points(database_name="discussion_database",
                                     content_type="discussion")


    if len(quiz_points) != expected_counts['quiz']:
        raise ValueError(f"unexpected quiz point count: {len(quiz_points)}")

    if len(discussion_points) != expected_counts['discussion']:
        raise ValueError(f"unexpected discussion point count: {len(discussion_points)}")

    upload_points(client,
                  quiz_points,
                  "quiz")
    
    upload_points(client,
                  discussion_points,
                  "discussion")

    final_counts = {
        content_type:count_content_types(client,content_type)
        for content_type in expected_counts

    }

    final_count = client.count(COLLECTION_NAME,exact=True).count

    print("\n poiints after upload:",final_count)
    print('final content counts:',final_counts)

    if final_counts != expected_counts:
        raise ValueError(f"final qdrantcontent counts mismatch:")

    if final_count != expected_final_count:
        raise ValueError(f"final qdrant content count {final_count} does not match expected {expected_final_count}")


    print('\n quiz and discussion qdrant intergartion completed successfully')


if __name__ == "__main__":
    main()
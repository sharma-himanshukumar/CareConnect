# Databricks notebook source
# MAGIC %md
# MAGIC # Expensive process run with patient

# COMMAND ----------

from openai import OpenAI
import os

class Embeddings:
    def __init__(self):
        self.client = OpenAI(
            api_key=dbutils.notebook.entry_point.getDbutils().notebook().getContext().apiToken().get(),
             base_url="https://dbc-65fcd381-2e74.cloud.databricks.com/serving-endpoints"
             )

    def get_embeddings(self, text):
        return self.client.embeddings.create(
            input=text,
            model="databricks-bge-large-en"
        )
# embeddings = Embeddings().get_embeddings("This is a test")
# print(len(embeddings.data[0].embedding))

# COMMAND ----------

# MAGIC %pip install --upgrade --force-reinstall databricks-vectorsearch
# MAGIC dbutils.library.restartPython()

# COMMAND ----------

# MAGIC %md
# MAGIC # Critical!! Vector DB creation and connection code
# MAGIC ## Handle with care, may break things.

# COMMAND ----------

from databricks.vector_search.client import VectorSearchClient

vsc = VectorSearchClient()

catalog_name = "careconnect"
schema_name = "default"
source_table_name = "careconnect_hospital_vector_db"
index_name = f"{catalog_name}.{schema_name}.{source_table_name}"
endpoint_name = "careconnect_endpoints"
default_argument = {
    "endpoint_name":endpoint_name,
    "index_name":index_name,
    "primary_key":"id",
    "embedding_dimension":1024,
    "embedding_vector_column":"embedding",
    "schema":{
    "id": "int",
    "chunk_id": "string",
    "page_number": "string",
    "hospital_name": "string",
    "text": "string",
    "location": "string",
    "embedding": "array<float>"}
    }

def call_index():
    try:
        index = vsc.create_direct_access_index(**default_argument)
        print(f"Index is ready.")
        return index
    except Exception as e:
        e= "RESOURCE_ALREADY_EXISTS"
        print("Index already exists")
        if "RESOURCE_ALREADY_EXISTS" in str(e):
            index = vsc.get_index(
                endpoint_name=endpoint_name,
                index_name=index_name
                )
        else:
            raise e
    index.wait_until_ready()
    print(f"Index is ready.")
    return index

def check_index(index):
    index_desc = index.describe()
    next_index = index_desc["status"]['index_row_count'] +1
    return next_index

def upsert_data():
    current_index = self.get_next_row() if idx_start is None else idx_start
    for chunk_id, chunk in enumerate(entries):
        try:
            chunk.update({"id": str(current_index)})
            self.index.upsert([chunk])
            current_index += 1

# COMMAND ----------

# MAGIC %md
# MAGIC # Running code....

# COMMAND ----------

# import
from openai import OpenAI
import os
import glob
import json
from datetime import datetime

# COMMAND ----------


class Embeddings:
    def __init__(self):
        self.client = OpenAI(
            api_key=dbutils.notebook.entry_point.getDbutils().notebook().getContext().apiToken().get(),
             base_url="https://dbc-65fcd381-2e74.cloud.databricks.com/serving-endpoints"
             )

    def get_embeddings(self, text):
        return self.client.embeddings.create(
            input=text,
            model="databricks-bge-large-en"
        )
        
def get_all_files():
    """
    Retrieves a list of all JSON files from a predefined directory.

    The directory path is hardcoded to '/Volumes/careconnect/default/input_data/'.
    
    Returns:
        list: A list of file paths (strings) for all .json files found.
              Returns an empty list if no files are found or if an error occurs.
    
    Raises:
        Prints an error message to the console if any unexpected error occurs
        during file globbing.
    """
    try:
        files = glob.glob('/Volumes/careconnect/default/input_data/*.json')
        return files
    except Exception as e:
        print(f"Error accessing directory or globbing files: {e}")
        return []

def generate_unique_chunk_id():
    """
    Generates a unique string ID based on the current datetime.

    The format is YYYYMMDDHHMMSSffffff (YearMonthDayHourMinuteSecondMicrosecond).

    Returns:
        str: A unique string identifier.
    
    Raises:
        Prints an error message to the console if datetime operations fail.
    """
    try:
        return datetime.now().strftime('%Y%m%d%H%M%S%f')
    except Exception as e:
        print(f"Error generating unique chunk ID: {e}")
        return "error_generating_id"

def read_files(data, file_name, embeddings):
    """
    Processes a list of data chunks, transforming them into a standardized format.

    Each chunk is augmented with a new unique chunk_id (original chunk_id + timestamp),
    page_number, and hospital_name (derived from the file_name).
    The remaining content of the chunk is converted to a JSON string.

    Args:
        data (list): A list of dictionaries, where each dictionary is an input data chunk.
                     Expected keys in each dictionary: 'chunk_id', 'page_number'.
        file_name (str): The path of the file from which the data was read.
                         Used to derive the hospital_name.

    Returns:
        list: A list of dictionaries, where each dictionary is a processed file_chunk.
              Returns an empty list if input data is invalid or an error occurs.
    
    Raises:
        Prints an error message to the console for various potential issues like
        invalid input data type, missing keys, or JSON serialization errors.
    """
    if not isinstance(data, list):
        print(f"Error: Input 'data' for file '{file_name}' is not a list.")
        return []

    file_data = []
    try:
        hospital_name_base = os.path.basename(file_name)
        hospital_name = os.path.splitext(hospital_name_base)[0].lower()
    except Exception as e:
        print(f"Error deriving hospital name from '{file_name}': {e}")
        hospital_name = "unknown_hospital"

    for i in data:
        if not isinstance(i, dict):
            print(f"Warning: Skipping non-dictionary item in data for file '{file_name}'. Item: {i}")
            continue
        
        file_chunk = {}
        try:
            original_chunk_id = i.get('chunk_id', 'unknown_id')
            file_chunk['chunk_id'] = f"{original_chunk_id}_{generate_unique_chunk_id()}"
            file_chunk['page_number'] = i.get('page_number', None)
            file_chunk['hospital_name'] = hospital_name
            file_chunk['location'] = "Delhi"
            content = i.copy()
            keys_to_remove = ['chunk_id', 'page_number', 'hospital_name', 'type', 
                              'hindi_message_title', 'hindi_message']
            for key in keys_to_remove:
                content.pop(key, None)
            
            file_chunk['text'] = json.dumps({i['type'] : content})
            file_chunk['embedding'] = embeddings.get_embeddings(file_chunk['text']).data[0].embedding
            file_data.append(file_chunk)
        except KeyError as ke:
            print(f"Warning: Missing key '{ke}' in chunk from file '{file_name}'. Chunk: {i}")
            continue
        except TypeError as te:
            print(f"Error serializing content to JSON for chunk '{original_chunk_id}' in file '{file_name}': {te}")
            continue
        except Exception as e:
            print(f"Unexpected error processing chunk from file '{file_name}': {e}. Chunk: {i}")
            continue 
            
    return file_data

def documnet_processing():
    """
    Main function to orchestrate the processing of JSON files.

    It gets all JSON files from the specified directory, reads each file,
    processes its content, and prints the first two processed chunks for each file.
    """
    embeddings = Embeddings()
    files = get_all_files()
    if not files:
        print("No JSON files found to process.")
        return

    final_data =[]
    for file_path in files:
        
        print(f"Start processing file {file_path}")
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                file_content_str = f.read()
        except FileNotFoundError:
            print(f"Error: File not found at '{file_path}'. Skipping.")
            continue
        except IOError as e:
            print(f"Error reading file '{file_path}': {e}. Skipping.")
            continue
        except Exception as e:
            print(f"An unexpected error occurred while opening/reading '{file_path}': {e}. Skipping.")
            continue

        try:
            data_from_json = json.loads(file_content_str)
        except json.JSONDecodeError as e:
            print(f"Error decoding JSON from file '{file_path}': {e}. Skipping.")
            continue
        except Exception as e:
            print(f"An unexpected error occurred while loading JSON from '{file_path}': {e}. Skipping.")
            continue
            
        processed_data = read_files(data_from_json, file_path, embeddings)
        if not processed_data:
            print(f"No valid data found in file '{file_path}'. Skipping.")
        else:
            final_data.extend(processed_data)
    return final_data


# COMMAND ----------

from databricks.vector_search.client import VectorSearchClient
from databricks.sdk.errors import ResourceAlreadyExists, NotFound
import time
import json
import logging

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class DatabricksVectorDBManager:
    """
    Manages operations for Databricks Vector Search, including index creation,
    status checking, and data upsertion for Direct Access Indexes.
    """
    def __init__(self,
                 endpoint_name: str,
                 catalog_name: str,
                 schema_name: str,
                 index_table_name: str, # Name for the table backing the index
                 embedding_dimension: 1024,
                 primary_key: str = "id",
                 embedding_vector_column: str = "embedding",
                 index_schema: dict = None
                 ):
        """
        Initializes the DatabricksVectorDBManager.

        Args:
            endpoint_name (str): The name of the Vector Search endpoint.
            catalog_name (str): The name of the Unity Catalog.
            schema_name (str): The name of the schema within the catalog.
            index_table_name (str): The name of the table that the index will be based on
                                   (used to construct the full index name).
            embedding_dimension (int): The dimension of the embedding vectors.
            primary_key (str, optional): The name of the primary key column. Defaults to "id".
            embedding_vector_column (str, optional): The name of the column containing
                                                     embedding vectors. Defaults to "embedding".
            index_schema (dict, optional): The schema definition for the Direct Access Index.
                                           If None, a default schema will be used.
                                           Example: {"id": "int", "text": "string", "embedding": "array<float>"}
        """
        try:
            self.vsc = VectorSearchClient()
            logger.info("VectorSearchClient initialized successfully.")
        except Exception as e:
            logger.error(f"Failed to initialize VectorSearchClient: {e}")
            raise

        self.endpoint_name = endpoint_name
        self.index_name = f"{catalog_name}.{schema_name}.{index_table_name}_idx"
        self.primary_key = primary_key
        self.embedding_dimension = embedding_dimension
        self.embedding_vector_column = embedding_vector_column
        self.upsert_stats = {
            "batch": {"successes": 0, "failures": 0},
            "total": {"successes": 0, "failures": 0}
        }

        if index_schema:
            self.index_schema = index_schema
        else:
            self.index_schema = {
                self.primary_key: "int", 
                "chunk_id": "string",
                "page_number": "string",
                "hospital_name": "string",
                "text": "string",
                "location": "string",
                self.embedding_vector_column: f"array<float>"
            }
        
        self.index = None

    def initialize_index(self, wait_for_readiness: bool = True, timeout_seconds: int = 300):
        """
        Creates a new Direct Access Vector Search Index or gets an existing one.

        Args:
            wait_for_readiness (bool, optional): Whether to wait for the index to become
                                                 ready after creation or retrieval. Defaults to True.
            timeout_seconds (int, optional): Maximum time in seconds to wait for the index
                                             to become ready. Defaults to 300.

        Returns:
            databricks.vector_search.index.VectorSearchIndex: The created or retrieved index object.

        Raises:
            Exception: If index creation fails for reasons other than already existing,
                       or if retrieval fails.
        """
        logger.info(f"Initializing index: {self.index_name} on endpoint: {self.endpoint_name}")
        try:
            self.index = self.vsc.create_direct_access_index(
                endpoint_name=self.endpoint_name,
                index_name=self.index_name,
                primary_key=self.primary_key,
                embedding_dimension=self.embedding_dimension,
                embedding_vector_column=self.embedding_vector_column,
                schema=self.index_schema
            )
            logger.info(f"Index {self.index_name} created successfully.")
        except Exception as e:
            e= "RESOURCE_ALREADY_EXISTS"
            if "RESOURCE_ALREADY_EXISTS" in str(e):
                try:
                    self.index = self.vsc.get_index(
                        endpoint_name=self.endpoint_name,
                        index_name=self.index_name
                    )
                    logger.info(f"Successfully fetched existing index: {self.index_name}")
                except NotFound:
                    logger.error(f"Index {self.index_name} reported as existing but then not found. This is unexpected.")
                    raise
                except Exception as e:
                    logger.error(f"Error fetching existing index {self.index_name}: {e}")
                    raise
        except Exception as e:
            logger.error(f"Failed to create or get index {self.index_name}: {e}")
            raise

        if self.index and wait_for_readiness:
            logger.info(f"Waiting for index {self.index_name} to be ready...")
            try:
                start_time = time.time()
                while True:
                    status = self.get_index_status()
                    if status and status.get("status", {}).get("ready", False):
                        logger.info(f"Index {self.index_name} is ready.")
                        break
                    if time.time() - start_time > timeout_seconds:
                        logger.error(f"Timeout waiting for index {self.index_name} to become ready.")
                        raise TimeoutError(f"Index {self.index_name} did not become ready within {timeout_seconds} seconds.")
            except Exception as e:
                logger.error(f"Error while waiting for index {self.index_name} to be ready: {e}")
                raise
        elif not self.index:
             logger.error(f"Index object for {self.index_name} could not be initialized.")
             raise ValueError(f"Index {self.index_name} could not be initialized.")


        return self.index

    def get_index_status(self):
        """
        Describes the current status and details of the initialized index.

        Returns:
            dict: A dictionary containing the index description, or None if an error occurs
                  or the index is not initialized.
        
        Raises:
            ValueError: If the index has not been initialized first.
        """
        if not self.index:
            logger.error("Index not initialized. Call initialize_index() first.")
            raise ValueError("Index not initialized. Call initialize_index() first.")
        try:
            status_description = self.index.describe()
            return status_description
        except Exception as e:
            logger.error(f"Error describing index {self.index_name}: {e}")
            return None 

    def get_next_row_id(self):
        """
        Determines the next available primary key ID for inserting a new row.
        This is typically the current row count if IDs are 0-indexed, or current_row_count
        if using auto-increment behavior (though direct access usually requires manual ID management).
        For simplicity and direct upsert, we assume IDs are managed externally or
        this reflects the number of documents. Vector Search itself doesn't auto-increment
        primary keys for Direct Access Indexes; the user provides the PK.
        This method will return the current number of rows, implying the next ID would be this number
        if using 0-based indexing for sequential IDs, or an arbitrary unique ID management system
        should be used by the caller.

        For this implementation, assuming `id` starts from 0 for the first document.
        So, the next `id` to be inserted is simply the current count of documents.

        Returns:
            int: The next ID to be used for a new row (current count of rows).
                 Returns 0 if the index is empty or status cannot be retrieved.
        
        Raises:
            ValueError: If the index has not been initialized first.
        """
        if not self.index:
            logger.error("Index not initialized. Call initialize_index() first.")
            raise ValueError("Index not initialized. Call initialize_index() first.")

        try:
            index_desc = self.get_index_status()
            if index_desc and index_desc.get("status"):
                row_count = index_desc["status"].get('indexed_row_count', 0)
                logger.info(f"Current row count for index {self.index_name} is {row_count}.")
                return int(row_count) +1
            else:
                logger.warning(f"Could not retrieve row count for index {self.index_name}. Assuming 0.")
        except Exception as e:
            logger.error(f"Error getting next row ID for index {self.index_name}: {e}")

    def upsert_data_batch(self, entries: list, batch_size: int = 10, id_start: int = None):
        """
        Upserts a list of data entries into the Vector Search Index in batches.
        Assigns a primary key 'id' to each entry, starting from id_start or
        from the next available ID based on the current index row count.

        Args:
            entries (list): A list of dictionaries, where each dictionary represents a document
                            to be upserted. Each entry should conform to the index schema
                            minus the primary key 'id', which will be added by this method.
            batch_size (int, optional): The number of entries to upsert in a single API call.
                                        Defaults to 100.
            id_start (int, optional): The starting ID for the primary key. If None,
                                      it will start from the next available ID in the index.
                                      It's the caller's responsibility to ensure these IDs are unique
                                      if providing them explicitly or if multiple processes write.

        Returns:
            bool: True if all batches were upserted successfully (or attempted), False otherwise.
        
        Raises:
            ValueError: If the index has not been initialized first or if entries is not a list.
        """
        if not self.index:
            logger.error("Index not initialized. Call initialize_index() first.")
            raise ValueError("Index not initialized. Call initialize_index() first.")
        if not isinstance(entries, list):
            logger.error("Entries to upsert must be a list of dictionaries.")
            raise ValueError("Entries to upsert must be a list of dictionaries.")
        if not entries:
            logger.info("No entries provided to upsert.")
            return True

        current_index = self.get_next_row_id() if id_start is None else id_start
        for chunk_id, chunk in enumerate(entries):
            try:
                chunk.update({"id": str(current_index)})
                self.index.upsert([chunk])
                current_index += 1
                self.upsert_stats["batch"]["successes"] += 1
                self.upsert_stats["total"]["successes"] += 1
            except Exception as e:
                self.upsert_stats["batch"]["failures"] += 1
                self.upsert_stats["total"]["failures"] += 1
                self.logger.info(
                    f"Error upserting document chunk {chunk_id} from {tag}: {str(e)}"
                    )
                
        return self.upsert_stats

    def similarity_search(self,
                          query_vector: list,
                          num_results: int = 5,
                          columns: list = None,
                          filters_json: str = None):
        """
        Performs a similarity search against the index.

        Args:
            query_vector (list): The embedding vector to query for.
            num_results (int, optional): The number of similar results to return. Defaults to 5.
            columns (list, optional): A list of column names to return in the results.
                                      If None, default columns might be returned by the API.
                                      Must include primary_key if you want it.
            filters_json (str, optional): JSON string representing filters to apply to the search.
                                          Example: '{"source_column = 'value'"}'

        Returns:
            dict: The search results from the API, or None if an error occurs.
        
        Raises:
            ValueError: If the index has not been initialized first.
        """
        if not self.index:
            logger.error("Index not initialized. Call initialize_index() first.")
            raise ValueError("Index not initialized. Call initialize_index() first.")

        if columns is None:
            columns = [self.primary_key] + [col for col in self.index_schema.keys() if col not in [self.primary_key, self.embedding_vector_column]]


        logger.info(f"Performing similarity search on index {self.index_name} for {num_results} results.")
        try:
            results = self.index.similarity_search(
                query_vector=query_vector,
                columns=columns,
                num_results=num_results,
                filters=filters_json
            )
            logger.info(f"Similarity search completed. Found {len(results.get('result', {}).get('data_array', []))} results.")
            return results
        except Exception as e:
            logger.error(f"Error during similarity search on index {self.index_name}: {e}")
            return None

def document_to_vector_db(sample_entries):
    ENDPOINT_NAME = "careconnect_endpoints" 
    CATALOG_NAME = "careconnect" 
    SCHEMA_NAME = "default"
    INDEX_TABLE_NAME = "careconnect_hospital_vector_db"
    EMBEDDING_DIM = 1024

    try:
        db_manager = DatabricksVectorDBManager(
            endpoint_name=ENDPOINT_NAME,
            catalog_name=CATALOG_NAME,
            schema_name=SCHEMA_NAME,
            index_table_name=INDEX_TABLE_NAME,
            embedding_dimension=EMBEDDING_DIM,
        )
        db_manager.initialize_index()
        logger.info(f"Index {db_manager.index_name} initialized.")
        status = db_manager.get_index_status()
        if status:
            logger.info(f"Index status: {status}")

        start_id = db_manager.get_next_row_id()
        logger.info(f"Next available ID for upsert: {start_id}")

        upsert_data = db_manager.upsert_data_batch(sample_entries, id_start=start_id)
        if upsert_data:
            logger.info(f"Sample data upserted (or attempted){upsert_data}.")
        else:
            logger.warning(f"Not all data batches were upserted successfully{upsert_data}.")

    except Exception as e:
        logger.error(f"An error occurred in the main execution block: {e}")

# COMMAND ----------

# MAGIC %md
# MAGIC # Run with care!! 
# MAGIC ## Below code will mvoe data to vector_DB

# COMMAND ----------

def start_extraction_and_push_to_db():
    documents= documnet_processing()
    document_to_vector_db(document)
start_extraction_and_push_to_db()

# COMMAND ----------

import pandas as pd
def call_vector_db(query, top_n):
        embeddings = Embeddings().get_embeddings(query)
        ENDPOINT_NAME = "careconnect_endpoints" 
        CATALOG_NAME = "careconnect" 
        SCHEMA_NAME = "default"
        INDEX_TABLE_NAME = "careconnect_hospital_vector_db"
        EMBEDDING_DIM = 1024
        db_manager = DatabricksVectorDBManager(
                endpoint_name=ENDPOINT_NAME,
                catalog_name=CATALOG_NAME,
                schema_name=SCHEMA_NAME,
                index_table_name=INDEX_TABLE_NAME,
                embedding_dimension=EMBEDDING_DIM,
        )
        db_manager.initialize_index()
        if db_manager.index:
                query_embedding = embeddings.data[0].embedding
                search_results = db_manager.similarity_search(
                query_vector=query_embedding,
                num_results=top_n,
                columns=["id", "text", "hospital_name"]
                )

        columns = [i['name'] for i in search_results['manifest']['columns']]
        data = [i for i in search_results['result']['data_array']]
        df = pd.DataFrame(data, columns=columns)
        return df

call_vector_db("give me hospital details", 3)

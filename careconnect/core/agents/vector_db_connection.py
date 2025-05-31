from databricks.vector_search.client import VectorSearchClient
from databricks.sdk.errors import ResourceAlreadyExists, NotFound
import time
import json
import logging
import pandas as pd
from openai import OpenAI
import os

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def refine_prompt_call_LLM(raw_query: str) -> str:
    """
    Calls the LLM endpoint to refine a raw user query into a concise search query.
    """
    DATABRICKS_TOKEN = dbutils.notebook.entry_point.getDbutils().notebook().getContext().apiToken().get()
    ENDPOINT_URL = "https://dbc-65fcd381-2e74.cloud.databricks.com/serving-endpoints"

    client = OpenAI(
        api_key=DATABRICKS_TOKEN,
        base_url=ENDPOINT_URL
    )

    system_message = (
        "You are an assistant that reformulates vague or conversational user messages into "
        "descriptive, focused queries suitable for searching a knowledge base or vector store. "
        "Be clear, specific, and include any location or context information provided."
        "Output only the final query, without quotes or formatting.\n\n"
        "Example:\n"
        "Input: 'Hi, I need some help, give me hospital doctors specialty for heart'\n"
        "Output: List of medical doctors specializing in cardiology or heart conditions at hospitals, including their credentials and subspecialties"
    )
    user_prompt = f"User message: \"{raw_query}\" \n\nProvide a detailed version of query, search-ready version of this query."

    messages = [
        {"role": "system", "content": system_message},
        {"role": "user", "content": user_prompt}
    ]

    response = client.chat.completions.create(
        model="databricks-claude-3-7-sonnet", 
        messages=messages
    )

    refined_query = response.choices[0].message.content.strip()
    return refined_query

class Embeddings:
    def __init__(self,api_key):
        self.client = OpenAI(
            api_key=api_key,
             base_url="https://dbc-65fcd381-2e74.cloud.databricks.com/serving-endpoints"
             )

    def get_embeddings(self, text):
        return self.client.embeddings.create(
            input=text,
            model="databricks-bge-large-en"
        )

class DatabricksVectorDBManager:
    """
    Manages operations for Databricks Vector Search, including index creation,
    status checking, and data upsertion for Direct Access Indexes.
    """
    def __init__(self,
                 endpoint_name: str,
                 catalog_name: str,
                 schema_name: str,
                 index_table_name: str,
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
                    f"Error upserting document chunk {chunk_id} from : {str(e)}"
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
            columns = [i['name'] for i in results['manifest']['columns']]
            data = [i for i in results['result']['data_array']]
            df = pd.DataFrame(data, columns=columns)
            return df
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


def call_vector_db(api_key, query, top_n):
        query = refine_prompt_call_LLM("Hi, I need a doctors in super specialty heart hospital")
        embeddings = Embeddings(api_key).get_embeddings(query)
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
            logger.info(f"Search results is ready: {search_results}")
        if not search_results.empty:
            return search_results.to_dict(orient="records")
        else:
            return {}



if __name__ == "__main__":
    # %pip install --upgrade --force-reinstall databricks-vectorsearch 
    # %pip install openai
    # dbutils.library.restartPython()
    api_key=dbutils.notebook.entry_point.getDbutils().notebook().getContext().apiToken().get()
    call_vector_db(api_key,"Hi, I need some help, give me hospital doctors specialty for heart", 5)

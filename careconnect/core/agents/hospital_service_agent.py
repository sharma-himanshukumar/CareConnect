import os
import sys
import json
import pandas as pd
from typing import TypedDict, Annotated, List, Union
from langchain_core.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI
from langgraph.graph import StateGraph, END
from openai import OpenAI
sys.path.append('/Workspace/Users/himanshuksharma@deloitte.com/CareConnect/careconnect')
from core.agents.vector_db_connection import Embeddings, call_vector_db

class AgentState(TypedDict):
    user_query: str
    route_decision: str  # e.g., "sql", "vector_db", "both", "general"
    sql_query: str
    sql_results: Union[List[dict], str, None] # Can be list of dicts or an error string
    vector_db_results: Union[pd.DataFrame, str, None] # Can be DataFrame or an error string
    final_answer: str
    error_message: str # To store any errors encountered

try:
    DATABRICKS_TOKEN = dbutils.notebook.entry_point.getDbutils().notebook().getContext().apiToken().get()
    if not DATABRICKS_TOKEN:
        raise ValueError("DATABRICKS_TOKEN is not set.")
except Exception as e:
    print(f"Error getting DATABRICKS_TOKEN: {e}. Please ensure it's correctly configured.")
    DATABRICKS_TOKEN = "dummy_token_if_testing_non_llm_parts"

DATABRICKS_SERVING_BASE_URL = "https://dbc-65fcd381-2e74.cloud.databricks.com/serving-endpoints"
YOUR_DATABRICKS_MODEL_ENDPOINT_NAME_FOR_CHAT = "databricks-claude-3-7-sonnet"

try:
    llm = ChatOpenAI(
        model_name=YOUR_DATABRICKS_MODEL_ENDPOINT_NAME_FOR_CHAT,
        openai_api_base=DATABRICKS_SERVING_BASE_URL, 
        openai_api_key=DATABRICKS_TOKEN,
        temperature=0.1, 
    )
    print(f"LangChain LLM (ChatOpenAI) configured for Databricks Model Serving endpoint: '{YOUR_DATABRICKS_MODEL_ENDPOINT_NAME_FOR_CHAT}' at '{DATABRICKS_SERVING_BASE_URL}'")
except Exception as e:
    print(f"Error initializing ChatOpenAI for Databricks Model Serving. Ensure endpoint name and token are correct. Error: {e}")




def generate_sql_query_node(state: AgentState):
    """
    Converts the user's natural language query to a SQL query using an LLM.
    """
    print("---AGENT: SQL Query Generator---")
    user_query = state["user_query"]
    system_message = """You are an intelligent SQL assistant for a healthcare data analytics platform running inside Databricks notebooks.
    Your job is to translate user questions into **pure SQL queries** that are ready to run in `%sql` cells inside Databricks.

    ### Available Tables
    The following tables are available in Unity Catalog under catalog `careconnect` and schema `default`.

    1. Table: `careconnect.default.all_india_hospital_list`
    - Columns:
        - Hospital Name (string)
        - Address (string)
        - CITY (string)
        - STATE (string)
        - PIN CODE (string)
        - PPN / NON PPN (string)
    - Description: Contains hospital information across India, useful for analyzing location, type (PPN/NON PPN), and accessibility of hospitals.

    2. Table: `careconnect.default.medical_conditions`
    - Columns:
        - condition_id (string)
        - user_id (string)
        - condition_name (string)
        - diagnosis_date (date)
        - is_chronic (boolean)
        - notes (string)
    - Description: Contains medical condition records for users, including diagnosis date and chronic status. 

    3. Table: `careconnect.default.users`
    - Columns:
        - user_id (string)
        - first_name (string)
        - last_name (string)
        - age (bigint)
        - gender (string)
        - email (string)
        - if_pregnant (boolean)
    - Description: Contains information about individual users including demographics and health status. It supports tracking patient details and tailoring healthcare services.

    ### Important Relationships
    - The `user_id` column in the `users` table uniquely identifies each user.
    - The `medical_conditions` table can have multiple rows per user because a user may have multiple medical conditions. Thus, `user_id` in `medical_conditions` is not unique.
    - Each row in `medical_conditions` is uniquely identified by the `condition_id` column.
    - Use these relationships to join tables when answering questions involving both users and their medical conditions.

    ### Rules:
    - Only generate **pure SQL queries** that will be executed in a `%sql` cell in a Databricks notebook.
    - Use **fully qualified table names** as listed above.
    - Do not explain the query.
    - Always wrap the SQL in triple backticks (```).
    - Use `LIMIT` to 10 in queries that return large result sets.
    - Make intelligent assumptions if some information is missing or unclear.
    Respond only with the SQL code block, and nothing else.
    """
    prompt = ChatPromptTemplate.from_messages([
        ("system", system_message),
        ("human", f"{user_query}")
    ])
    if not llm:
        return {"sql_query": None, "error_message": "LLM not initialized for SQL generation."}

    try:
        chain = prompt | llm
        response = chain.invoke({"user_query": user_query})
        sql_query = response.content.strip()
        if sql_query == "CANNOT_ANSWER_WITH_SQL":
            print(f"LLM determined it cannot answer with SQL: {user_query}")
            return {"sql_query": None, "sql_results": "Query not suitable for SQL based on schema."}
        sql_query = sql_query.split("```")[1].strip() if "```" in sql_query else sql_query
        sql_query = sql_query.replace("sql", "").strip() + ";"
        return {"sql_query": sql_query}
    except Exception as e:
        print(f"Error in SQL generation: {e}")
        return {"sql_query": None, "error_message": f"SQL generation failed: {str(e)}"}

def execute_sql_node(state: AgentState):
    """
    Executes the generated SQL query.
    """
    print("---AGENT: SQL Executor---")
    sql_query = state.get("sql_query")
    if not sql_query:
        print("No SQL query to execute.")
        return {"sql_results": "No SQL query provided."}

    try:
        df = spark.sql(sql_query)
        df=df.toPandas()
        results = df.to_dict(orient="records")
        return {"sql_results": results}
    except Exception as e:
        print(f"Error executing SQL: {e}")
        return {"sql_results": f"SQL execution error: {str(e)}"}

def vector_db_search_node(state: AgentState):
    """
    Performs a search on the vector database.
    """
    print("---AGENT: Vector DB Searcher---")
    user_query = state["user_query"]
    try:
        result = call_vector_db(api_key, user_query, 5)
        return {"vector_db_results":result}
    except Exception as e:
        print(f"Error in Vector DB search: {e}")
        return {"vector_db_results": f"Vector DB search error: {str(e)}"}


def query_router_node(state: AgentState):
    """
    Decides which data source(s) to query based on the user's query.
    """
    print("---AGENT: Query Router---")
    user_query = state["user_query"]
    prompt_text = f"""
    You are an intelligent routing agent. Your task is to determine the most appropriate data source for a given user query.

    The available data sources are:

    1. SQL_DATABASE: Contains structured data in three main tables:
    - users: Personal and health-related details of individuals, such as name, age, gender, email, and health status including pregnancy.
    - medical_conditions: Medical condition records for users, including condition name, diagnosis date, and chronic status.
    - all_india_hospital_list: Directory of hospitals across India with name, address, city, state, pin code, and type (PPN or NON PPN).
    - Best used for: exact lookups, filtering, aggregations (e.g., COUNT, SUM), user demographics, condition tracking, hospital listings.
    - Example queries: "List pregnant users under 30.", "Find users diagnosed with diabetes.", "Hospitals in Delhi that are PPN."

    2. VECTOR_DATABASE: Contains semantically searchable hospital brochure documents. These include:
    - Hospital services, departments, specialties, available doctors, pathology labs, diagnostic facilities, and other general healthcare information.
    - Best used for: semantic search, broad or unstructured queries, questions about services, specialties, or descriptive content.
    - Example queries: "Tell me about cardiology facilities.", "What lab tests are available?", "Do they offer cancer treatment?"

    3. BOTH: When the query involves a combination of structured data and semantic content from brochures.
    - Example: "Show me hospitals in Bangalore and tell me what pediatric services they offer."

    4. GENERAL: For casual, non-informational, or irrelevant questions that are conversational or outside the domain of the databases.
    - Example: "Hello", "What's the weather today?"

    Analyze the following user query: "{user_query}"
    Respond with only one of the following keywords: SQL_DATABASE, VECTOR_DATABASE, BOTH, GENERAL.
    """
    if not llm:
        return {"route_decision": "GENERAL", "error_message": "LLM not initialized for routing."}

    try:
        response = llm.invoke(prompt_text)
        decision = response.content.strip().upper()
        print(f"Router decision: {decision}")
        if decision not in ["SQL_DATABASE", "VECTOR_DATABASE", "BOTH", "GENERAL"]:
            print(f"Router made an invalid decision: {decision}. Defaulting to GENERAL.")
            decision = "GENERAL"
        return {"route_decision": decision}
    except Exception as e:
        print(f"Error in query routing: {e}")
        return {"route_decision": "GENERAL", "error_message": f"Routing failed: {str(e)}"}

def answer_synthesizer_node(state: AgentState):
    """
    Synthesizes a final answer from the retrieved data or indicates if it cannot answer.
    """
    print("---AGENT: Answer Synthesizer---")
    user_query = state["user_query"]
    sql_results = state.get("sql_results")
    vector_db_results = state.get("vector_db_results")
    route = state.get("route_decision")

    context_parts = [f"Original user query: {user_query}"]

    if route == "GENERAL" and not sql_results and not vector_db_results:
        prompt_text = f"The user asked: '{user_query}'. This query was deemed general and not suitable for our databases. Can you provide a general response or indicate you cannot answer with specific data?"
        if not llm:
            return {"final_answer": "I'm sorry, the LLM is not available to process this general query."}
        try:
            response = llm.invoke(prompt_text)
            return {"final_answer": response.content}
        except Exception as e:
            return {"final_answer": f"Error processing general query: {str(e)}"}


    if isinstance(sql_results, str):
        context_parts.append(f"SQL Database Access Note: {sql_results}")
    elif sql_results:
        context_parts.append(f"Information from SQL Database:\n{json.dumps(sql_results, indent=2)}")

    if isinstance(vector_db_results, str):
        context_parts.append(f"Vector Database Access Note: {vector_db_results}")
    elif vector_db_results:
        vdb_summary = []
        for item in vector_db_results[:3]:
            vdb_summary.append(f"- Chunk ID: {item.get('chunk_id', 'N/A')}, Text Snippet: {item.get('text', 'N/A')[:100]}...")
        context_parts.append(f"Information from Vector Database (Top 3 snippets):\n" + "\n".join(vdb_summary))

    if len(context_parts) == 1:
        error_msg = state.get("error_message", "I could not retrieve relevant information from the databases.")
        return {"final_answer": f"I'm sorry, I couldn't find an answer to your query. {error_msg}"}

    final_prompt_text = f"""
    Based on the following information, provide a comprehensive answer to the user's query.
    If the information is insufficient or there were errors accessing data, state that.
    Context:
    "\n\n".join({context_parts})
    Provide a final answer to the user.
    """
    if not llm:
        return {"final_answer": "I'm sorry, the LLM is not available to synthesize the answer."}

    try:
        response = llm.invoke(final_prompt_text)
        print(f"Synthesized Answer: {response.content}")
        return {"final_answer": response.content}
    except Exception as e:
        print(f"Error in answer synthesis: {e}")
        return {"final_answer": f"Error synthesizing answer: {str(e)}"}

def decide_next_step(state: AgentState):
    """
    Determines the next node based on the router's decision.
    """
    print(f"---ROUTING LOGIC based on: {state['route_decision']}---")
    if state.get("error_message"):
        print("Error detected, routing to synthesizer to report.")
        return "synthesizer"

    route = state["route_decision"]
    if route == "SQL_DATABASE":
        return "sql_generator"
    elif route == "VECTOR_DATABASE":
        return "vector_db_searcher"
    elif route == "BOTH":
        return "sql_generator"
    elif route == "GENERAL":
        return "synthesizer"
    return END 

def after_sql_execution(state: AgentState):
    """
    Decides where to go after SQL execution. If 'BOTH' was chosen, go to vector DB.
    Otherwise, go to synthesizer.
    """
    print("---LOGIC: After SQL Execution---")
    if state.get("error_message") or isinstance(state.get("sql_results"), str):
        print("Error in SQL path or SQL not suitable, proceeding to synthesizer or VDB if 'BOTH'.")

    if state["route_decision"] == "BOTH":
        return "vector_db_searcher"
    return "synthesizer"


workflow = StateGraph(AgentState)
workflow.add_node("router", query_router_node)
workflow.add_node("sql_generator", generate_sql_query_node)
workflow.add_node("sql_executor", execute_sql_node)
workflow.add_node("vector_db_searcher", vector_db_search_node)
workflow.add_node("synthesizer", answer_synthesizer_node)

workflow.set_entry_point("router")

workflow.add_conditional_edges(
    "router",
    decide_next_step,
    {
        "sql_generator": "sql_generator",
        "vector_db_searcher": "vector_db_searcher",
        "synthesizer": "synthesizer",
        END: END
    }
)

workflow.add_edge("sql_generator", "sql_executor")
workflow.add_conditional_edges(
    "sql_executor",
    after_sql_execution,
    {
        "vector_db_searcher": "vector_db_searcher",
        "synthesizer": "synthesizer"
    }
)
workflow.add_edge("vector_db_searcher", "synthesizer")
workflow.add_edge("synthesizer", END)

app = workflow.compile()

def run_query(user_input_query):
    if not llm:
        print("LLM is not initialized. Cannot run query.")
        return "LLM not available."

    inputs = {"user_query": user_input_query}
    final_state = app.invoke(inputs)
    return final_state.get("final_answer", "No answer synthesized.")

if __name__ == "__main__":
    %pip install --disable-pip-version-check -q langchain_core langchain_openai langgraph
    %pip install --upgrade --force-reinstall -q databricks-vectorsearch
    dbutils.library.restartPython()
    query1 = "Hi, I'm in Delhi, feeling heaveness in my heart and I want to know about the nearest hospital and contact details"
    print(f"\n\n--- Running Query 1: '{query1}' ---")
    answer1 = run_query(query1)
    print(f"\nFinal Answer for Query 1:\n{answer1}")

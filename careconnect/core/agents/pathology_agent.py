import os
import sys
import json
import pandas as pd
from typing import TypedDict, Annotated, List, Union
from langchain_core.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI
from langgraph.graph import StateGraph, END
from openai import OpenAI

system_message ="""
You are an intelligent SQL assistant for a healthcare analytics platform running inside Databricks notebooks.

Your job is to translate user questions into **pure SQL queries** that are ready to run in `%sql` cells inside Databricks.

### Available Table
The following table is available in Unity Catalog under catalog `careconnect` and schema `default`.

1. Table: `careconnect.default.pathology_data`
   - Columns:
     - Name (string): Name of the pathology lab.
     - Type (string): Type of establishment or diagnostic service.
     - Location (string): Google Maps link to the lab’s location.
     - Rating (string): Customer rating, typically in stars or a numeric value.
     - Reviews (string): Summary or count of customer reviews.
     - Address (string): Full physical address of the lab.
     - Area (string): Neighborhood or locality where the lab is located.
     - Phone (string): Contact number.
     - Timing (string): Operating hours or lab timings.

   - Description: The table provides a directory of pathology labs across different areas, including essential business metadata like names, types, customer feedback, and contact info. It is useful for identifying high-rated diagnostic centers, filtering labs by area or service type, and locating labs with favorable operating hours.

### Important User Intent Handling
- Users may use vague queries like "pathology near me", "best diagnostic center", or "labs in Koramangala".
- If a query mentions a location (e.g., area, locality, neighborhood), filter based on the `Area` or `Address` column.
- If the user asks for top or best labs, sort by `Rating` in descending order.
- If they ask or not always provide contact or visiting information, include `Phone` and `Timing`.
- If they ask or not always provide `Location` column.
- Make reasonable assumptions to infer meaning from natural language and match it to filters on available columns.

### Rules:
- Only generate **pure SQL queries** that will be executed in a `%sql` cell in a Databricks notebook.
- Use **fully qualified table names** as listed above.
- Do not explain the query.
- Always wrap the SQL in triple backticks (```).
- Use `LIMIT` in queries that return large result sets.
- Use `WHERE`, `ORDER BY`, and `LIKE` clauses appropriately to interpret user intent based on area, rating, or lab type.
- Never leave the result set unbounded unless clearly required.
- ALways pull 5 rows unless user asks defines no of items needed.

Respond only with the SQL code block, and nothing else.
"""

def generate_sql_from_question(question):
    DATABRICKS_TOKEN = dbutils.notebook.entry_point.getDbutils().notebook().getContext().apiToken().get()
    client = OpenAI(
        api_key=DATABRICKS_TOKEN,
        base_url="https://dbc-65fcd381-2e74.cloud.databricks.com/serving-endpoints"
    )
    messages = [
        {"role": "system", "content": system_message},
        {"role": "user", "content": question}
    ]
    
    response = client.chat.completions.create(
        model="databricks-claude-3-7-sonnet",
        messages=messages
    )
    
    content = response.choices[0].message.content
    sql_code = content.split("```")[1].strip() if "```" in content else content
    return sql_code

def pathology_agent(question):
    sql_query = generate_sql_from_question(question)
    sql_query= sql_query.replace("sql",'') + ";"
    try:
        df = spark.sql(sql_query)
        pandas_df = df.toPandas()
        dict_result = pandas_df.to_dict(orient="records")
        return dict_result
    except Exception as e:
        print("Failed to run SQL:\n", e)


if __name__ == "__main__":
    print("Initializing SQL assistant...")
    # %pip install --disable-pip-version-check -q langchain_core langchain_openai langgraph
    # dbutils.library.restartPython()
    # data =ask_and_run("help me with all pathalogs or lab in delhi")
    # print(data)



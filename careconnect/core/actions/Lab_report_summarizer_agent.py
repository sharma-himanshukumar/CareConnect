# Databricks notebook source
# MAGIC %pip install --disable-pip-version-check -q langchain_core langchain_openai langgraph pymupdf python-docx
# MAGIC
# MAGIC dbutils.library.restartPython()

# COMMAND ----------

import os
import sys
import fitz
import json
from docx import Document 
from typing import TypedDict, Annotated, List, Union, TypedDict, Optional, Annotated
from langchain_core.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI
from langgraph.graph import StateGraph, END
from openai import OpenAI
sys.path.append('/Workspace/Users/himanshuksharma@deloitte.com/CareConnect/careconnect')

# COMMAND ----------

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

# COMMAND ----------

class AgentState(TypedDict):
    uploaded_file: Optional[str]
    file_path: Optional[str]
    raw_lab_text: Optional[str]
    cleaned_lab_data: Optional[str]
    lab_summary: Optional[str]
    final_answer: Optional[str]
    error_message: Optional[str] 

# COMMAND ----------

def file_uploader_node(state: AgentState) -> AgentState:
    print("---EXECUTING FILE UPLOADER NODE---")
    file = state.get("uploaded_file")
    if not file:
        return {"error_message": "No file uploaded."}
    if not os.path.exists(file):
        return {"error_message": f"File not found at path: {file}"}
    return {"file_path": file, "error_message": None}

def file_extractor_node(state: AgentState) -> AgentState:
    print("---EXECUTING FILE EXTRACTOR NODE---")
    if state.get("error_message"): 
        return {}
    file_path = state.get("file_path")
    if not file_path:
        return {"error_message": "File path not provided to extractor."}

    try:
        text = ""
        if file_path.endswith(".pdf"):
            doc = fitz.open(file_path)
            for page in doc:
                text += page.get_text() + "\n"
            doc.close()
        elif file_path.endswith(".docx"):
            doc = Document(file_path)
            text = "\n".join(p.text for p in doc.paragraphs)
        else:
            return {"error_message": "Unsupported file format. Only .pdf and .docx are supported."}
        
        if not text.strip():
            return {"error_message": "No text could be extracted from the file."}
        return {"raw_lab_text": text, "error_message": None}
    except Exception as e:
        return {"error_message": f"File extraction error: {str(e)}"}

def lab_report_cleaner_node(state: AgentState) -> AgentState:
    print("---EXECUTING LAB REPORT CLEANER NODE---")
    if state.get("error_message"):
        return {}
    raw_text = state.get("raw_lab_text", "")
    if not raw_text:
        return {"error_message": "No text extracted from lab report to clean."}

    cleaned_text = raw_text.replace('\n\n', '\n').replace('  ', ' ').strip()
    cleaned_text = "\n".join([line.strip() for line in cleaned_text.split('\n') if line.strip()])

    print(f"Cleaned text preview (first 500 chars):\n{cleaned_text[:500]}")
    return {"cleaned_lab_data": cleaned_text, "error_message": None}

def lab_summary_node(state: AgentState) -> AgentState:
    print("---EXECUTING LAB SUMMARY NODE---")
    if state.get("error_message"):
        return {}
    cleaned_data = state.get("cleaned_lab_data", "")
    if not cleaned_data:
        return {"error_message": "No cleaned lab data to summarize."}

    prompt = f"""
    You are an expert medical assistant AI. A patient has uploaded their lab report.
    Here is the extracted and cleaned data from their lab report:

    <lab_report_data>
    {cleaned_data}
    </lab_report_data>

    Your task is to analyze this lab report data and provide a summary for the patient.
    Please explain the findings in simple, clear, non-technical language that a layperson can easily understand.
    For each significant test or group of tests mentioned:
    1. Briefly explain what the test is for (its purpose).
    2. Indicate whether the result appears to be within a normal range, high, or low. If reference ranges are provided in the text, use them. If not, use general medical knowledge.
    3. Explain the potential implications of any abnormal results in simple terms.
    4. Explicitly state if a result needs medical attention or follow-up with a doctor.

    Structure your summary clearly. Be concise but informative. Avoid medical jargon where possible, or explain it if unavoidable.
    If the provided data is insufficient or seems corrupted for a comprehensive analysis, please state that.
    Do not provide medical advice or diagnosis, but rather explain the report and suggest when to consult a healthcare professional.
    Start your response with a general overview and then go into specifics.
    """
    try:
        response = llm.invoke(prompt)
        return {"lab_summary": response.content, "error_message": None}
    except Exception as e:
        return {"error_message": f"LLM summarization failed: {str(e)}"}

def lab_final_response_node(state: AgentState) -> AgentState:
    print("---EXECUTING FINAL RESPONSE NODE---")
    if state.get("error_message"):
        return {"final_answer": f"Could not complete analysis. Error: {state['error_message']}"}
    
    summary = state.get("lab_summary")
    if not summary:
        return {"final_answer": "No summary was generated. There might have been an issue in a previous step."}
    return {"final_answer": summary}

workflow = StateGraph(AgentState)

# Add nodes
workflow.add_node("file_uploader", file_uploader_node)
workflow.add_node("file_extractor", file_extractor_node)
workflow.add_node("lab_cleaner", lab_report_cleaner_node)
workflow.add_node("lab_summarizer", lab_summary_node)
workflow.add_node("responder", lab_final_response_node)

# Set entry and edges
workflow.set_entry_point("file_uploader")
workflow.add_edge("file_uploader", "file_extractor")
workflow.add_edge("file_extractor", "lab_cleaner")
workflow.add_edge("lab_cleaner", "lab_summarizer")
workflow.add_edge("lab_summarizer", "responder")
workflow.add_edge("responder", END)

# Compile the graph
app = workflow.compile()

# 4. Function to run the analysis
def run_lab_report_analysis(file_path_to_analyze: str):
    inputs = {"uploaded_file": file_path_to_analyze}
    final_state = None
    for event in app.stream(inputs, {"recursion_limit": 10}):
        for key, value in event.items():
            print(f"---EVENT FROM NODE: {key}---")
            if 'error_message' in value and value['error_message']:
                print(f"ERROR: {value['error_message']}")
            if 'final_answer' in value:
                final_state = value
    
    if final_state and final_state.get("final_answer"):
        return final_state["final_answer"]
    elif final_state and final_state.get("error_message"):
        return f"Analysis failed. Error: {final_state.get('error_message')}"
    return "No response generated, and no specific error reported in final state."


# COMMAND ----------


print("\n--- Analyzing PDF Report ---")
file ="/Volumes/careconnect/default/lab_reports/CBC-test-report-format-example-sample-template-Drlogy-lab-report.pdf"
if os.path.exists(file):
    pdf_report_path = file
    pdf_summary = run_lab_report_analysis(pdf_report_path)
    print("\nFINAL PDF SUMMARY:\n", pdf_summary)
else:
    print("dummy_lab_report.pdf not found, skipping PDF analysis.")

# COMMAND ----------



# COMMAND ----------



# COMMAND ----------

# MAGIC %md
# MAGIC # Data crawler to find pathology 

# COMMAND ----------

API_URL = "https://nearby.pathkindlabs.com/?page=1"

import requests
import pandas as pd
import time

# You'll need to populate this list with cities you want to search for.
# This is the trickiest part for getting "all" data, as you need to know which cities they serve.
# CITIES_TO_SEARCH = [
#     "Delhi", "Mumbai", "Bangalore", "Kolkata", "Chennai",
#     "Hyderabad", "Pune", "Ahmedabad", "Jaipur", "Lucknow",
#     "Noida", "Gurgaon", "Ghaziabad", "Faridabad", "Chandigarh",
#     "Mohali", "Patna", "Bhopal", "Indore", "Ludhiana", "Agra"
#     # Add more cities as needed
# ]

all_labs_data = []

headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
    "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8", # From inspecting the request
    "X-Requested-With": "XMLHttpRequest" # Often present for AJAX requests
}

# for city in CITIES_TO_SEARCH:
    # print(f"Fetching labs for: {city}...")
    # payload = {"city": city}

    # try:
response = requests.get(API_URL)
response.raise_for_status()  # Raise an exception for HTTP errors (4xx or 5xx)
# data = response.json() if response.text else {}
print(response.text)

    #     if data.get("status") and data.get("data"):
    #         labs_in_city = data["data"]
    #         print(f"Found {len(labs_in_city)} labs in {city}.")
    #         for lab in labs_in_city:
    #             lab['searched_city'] = city # Add the city we searched for, useful for context
    #         all_labs_data.extend(labs_in_city)
    #     elif not data.get("status"):
    #         print(f"API reported an error for {city}: {data.get('message', 'No message')}")
    #     else:
    #         print(f"No labs found or unexpected data structure for {city}.")

    # except requests.exceptions.RequestException as e:
    #     print(f"Request failed for {city}: {e}")
    # except ValueError as e: # Includes JSONDecodeError
    #     print(f"Could not decode JSON for {city}: {e}")
    #     print(f"Response text: {response.text[:200]}...") # Print a snippet of the problematic response


#     time.sleep(1) # Be polite to the server, wait 1 second between requests

# # Convert the list of dictionaries to a Pandas DataFrame
# if all_labs_data:
#     df = pd.DataFrame(all_labs_data)

#     # Display some info about the DataFrame
#     print("\n--- Data Summary ---")
#     print(f"Total labs fetched: {len(df)}")
#     print("Columns found:", df.columns.tolist())
#     print("\nFirst 5 rows:")
#     print(df.head())

#     # Save to CSV
#     try:
#         df.to_csv("pathkind_labs_data.csv", index=False, encoding='utf-8-sig')
#         print("\nData successfully saved to pathkind_labs_data.csv")
#     except Exception as e:
#         print(f"\nError saving to CSV: {e}")
# else:
#     print("\nNo data was fetched.")

# COMMAND ----------

response.raise_for_status() or response.json()

# COMMAND ----------

    import requests
from bs4 import BeautifulSoup

def fetch_html(url):
    """Fetches HTML content from a given URL."""
    try:
        # Add a User-Agent header to mimic a browser
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        }
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()  # Raise an exception for bad status codes (4xx or 5xx)
        return response.text
    except requests.exceptions.RequestException as e:
        print(f"Error fetching URL {url}: {e}")
        return None

def extract_data_from_example_com(html_content):
    """Extracts specific data from example.com."""
    if not html_content:
        return None

    soup = BeautifulSoup(html_content, 'html.parser') # 'lxml' is faster if installed

    extracted_data = {}

    # 1. Get the page title
    title_tag = soup.find('title')
    extracted_data['title'] = title_tag.string if title_tag else "No title found"

    # 2. Get the main heading (h1)
    h1_tag = soup.find('h1')
    extracted_data['heading'] = h1_tag.string if h1_tag else "No H1 found"

    # 3. Get the text from the first paragraph
    p_tag = soup.find('p')
    extracted_data['first_paragraph'] = p_tag.get_text(strip=True) if p_tag else "No paragraph found"

    # 4. Get all links
    links = []
    for a_tag in soup.find_all('a', href=True): # Find all <a> tags with an href attribute
        links.append({
            'text': a_tag.string if a_tag.string else "No link text",
            'url': a_tag['href']
        })
    extracted_data['links'] = links

    return extracted_data

def extract_quotes_from_toscrape_com(html_content):
    """Extracts quotes from quotes.toscrape.com."""
    if not html_content:
        return []

    soup = BeautifulSoup(html_content, 'html.parser')
    quotes_data = []

    # Each quote is within a div with class 'quote'
    quote_divs = soup.find_all('div', class_='quote')

    for quote_div in quote_divs:
        text_span = quote_div.find('span', class_='text')
        author_small = quote_div.find('small', class_='author')
        tags_div = quote_div.find('div', class_='tags')

        tags = [tag.get_text(strip=True) for tag in tags_div.find_all('a', class_='tag')] if tags_div else []

        quotes_data.append({
            'text': text_span.get_text(strip=True) if text_span else "N/A",
            'author': author_small.get_text(strip=True) if author_small else "N/A",
            'tags': tags
        })
    return quotes_data


example_url = "http://example.com"
html_example = fetch_html(example_url)

if html_example:
    data_example = extract_data_from_example_com(html_example)


# COMMAND ----------



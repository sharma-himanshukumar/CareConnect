# 🏥 CareConnect

**Category:** Healthcare  
**Hackathon Project**

CareConnect is an all-in-one healthcare assistance platform designed to provide quick, concise, and reliable information tailored to a user's needs. Whether you're searching for nearby hospitals specialising in cardiac care or looking for pathology labs around you, CareConnect is here to help.
Contributor:- Himanshu Kumar Sharma, Ashish Gupta
---

## 🚀 Overview

CareConnect aims to be a go-to companion for everyday healthcare queries. It empowers users by:

- Locating hospitals by treatment specialization
- Recommending pathology labs near you
- Simplifying lab reports and medical test results
- Suggesting medications based on symptoms, age, and health context

By combining accessibility with personalized health insights, CareConnect helps users make informed healthcare decisions—anytime, anywhere.

---

## 🤖 Agents (Powered by LangGraph)

### 🏥 1. Hospital Agent

Provides users with comprehensive, location-based information about hospitals.

#### 🔧 Implementation:

- **Data Collection & Storage:**  
  Hospital data (name, location, city, services) stored in a SQL database on Databricks Unity Catalog.

- **Brochure Parsing & Vectorization:**  
  Brochures containing doctor details, fees, bed count, etc., are parsed and embedded into Databricks VectorDB.

- **Use Cases:**
  - **Location-Based Search:**  
    _"Show me all hospitals in Delhi"_ → Returns filtered SQL data.
  - **Specialization-Based Query:**  
    _"Which doctors specialize in bone treatment?"_ → Uses VectorDB for semantic results.
  - **Symptom-Based Assistance:**  
    _"I feel heaviness on the left side of my body."_ → Recommends nearby cardiology hospitals based on SQL + VectorDB data.

#### ✅ Example Output:
> _“Based on your symptoms, we recommend visiting the following cardiology-specialized hospitals near you. Dr. A (MBBS, MD, 15+ yrs experience) is available until 5 PM. Consultation fee: ₹300.”_

---

### 🧪 2. Lab & Pathology Agent

Helps users find diagnostic labs near their location using location and time-aware filters.

#### 🔧 Implementation:

- **Data Ingestion:**  
  Lab name, address, operating hours, and Google Maps links are stored in Databricks tables.

- **Use Cases:**
  - **Smart Filtering:**  
    Considers current time and location to show only open labs.

#### ✅ Example Output:
> _“Here are labs near you currently open:  
- City Path Lab, ABC Road – Open till 8 PM – [View on Map]  
- HealthFirst Diagnostics, XYZ Lane – Open till 6 PM – [View on Map]”_

---

### 📄 3. Lab Report Summarizer Agent

Simplifies complex lab reports and diagnostic values into layman-friendly language.

#### 🔧 Implementation:

1. **File Upload & Parsing:**  
   Parses PDF/image reports using OCR/document parsers.
2. **Medical Analysis:**  
   Compares extracted values with standard ranges.
3. **Natural Language Summary:**  
   Explains significance of values and flags abnormalities.

#### ✅ Example Output:
> _“Your haemoglobin is slightly below normal. This may indicate mild anaemia. Please consult your doctor and consider an iron-rich diet.”_

---

### 💊 4. Medication Advisor Agent

Suggests safe and personalized medicines based on symptoms, age, gender, pregnancy status, and time of day.

#### 🔧 Implementation:

- **Data Includes:**
  - Medicine names & compositions
  - Dosage by age group
  - Restrictions (e.g., pregnancy, elderly)
  - Time-sensitive recommendations

- **Steps:**
  1. User context detection (age, gender, time)
  2. Semantic retrieval from VectorDB
  3. Safe medication recommendations

#### ✅ Example Output:
> _“You are 29, female, and pregnant. Do not self-medicate. Paracetamol (low dose) might be prescribed under doctor supervision.”_

> _“You have a mild fever. You can take Paracetamol 500mg every 6 hours for 2–3 days. Stay hydrated and consult a doctor if it persists.”_

---

## 📦 Tech Stack

- **LLM Orchestration:** LangGraph  
- **Data Processing & Storage:** Databricks (SQL Tables, Unity Catalog, VectorDB)  
- **Embedding & Retrieval:** VectorDB with semantic search  
- **Parsing:** PDF parsers, OCR for report extraction  
- **User Input:** Natural Language (chat interface)

---

## 💡 Why CareConnect?

Healthcare can be complex. CareConnect bridges that gap using AI—by providing:

- Personalized, safe advice
- Contextual and real-time insights
- Simplified explanations for non-technical users

It’s not just about giving answers, it’s about delivering **the right** answers—**responsibly**.

---

## 🙌 Team

Built as part of a healthcare hackathon with a focus on impact, accessibility, and innovation.

---


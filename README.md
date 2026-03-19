<div align="center">
  <img src="https://img.shields.io/badge/Status-Active-brightgreen?style=for-the-badge" alt="Status" />
  <img src="https://img.shields.io/badge/Version-1.0.0-blue?style=for-the-badge" alt="Version" />
  <img src="https://img.shields.io/badge/License-MIT-purple?style=for-the-badge" alt="License" />
</div>

<h1 align="center">🚀 LogiSense AI Unified Platform</h1>

<p align="center">
  <b>An End-to-End AI Logistics OS</b> combining Predictive Analytics, the Zen Platform (ZenDec, ZenRTO, ZenETA), and Advanced Agentic Intelligence.
</p>

---

## 🌟 Overview

LogiSense AI Unified Platform is a next-generation logistics command center. It leverages bleeding-edge machine learning and agentic AI to autonomously monitor, predict, and resolve supply chain disruptions in real-time. By integrating a monolithic FastAPI backend with a sleek, minimalist Next.js/React frontend, LogiSense offers unparalleled visibility and automated recovery strategies across the entire logistics lifecycle.

![Logistics Hero](https://images.unsplash.com/photo-1586528116311-ad8dd3c8310d?q=80&w=1000&auto=format&fit=crop) *(Illustrative image — Replace with your actual dashboard screenshot)*

---

## 🏗️ Platform Architecture

The LogiSense architecture is built for **scale** and **resilience**, operating via a synchronized frontend and backend that communicate through WebSocket streams and robust REST APIs.

### The Agentic Core

| Module | Purpose & Function | Tech Stack / Models |
| :--- | :--- | :--- |
| **🔍 Observer (F1/F4)** | Real-time Anomaly Detection & Warehouse Load Polling. Continuously monitors streams for deviations. | *Isolation Forest, ARIMA(1,1,1)* |
| **🧠 Reasoner (F2)** | Supply Chain Contagion Risk Analysis & Cascade Trees. Evaluates downstream impact. | *Directed Acyclic Graph (DAG) BFS, LightGBM* |
| **⚡ Actor (F3/F4)** | Autonomous Carrier Subbing, Rerouting & Intake Staggering. Executes recovery workflows. | *Kolmogorov–Smirnov Drift, Heuristics* |

### The Zen Platform

| Module | Purpose & Function | Tech Stack / Models |
| :--- | :--- | :--- |
| **⚖️ ZenDec (F6)** | Route & Carrier Decision Engine. Multi-criteria optimization balancing cost, SLA, and AQI. | *TOPSIS Optimization, AQI APIs, GenAI* |
| **🛡️ ZenRTO (F6)** | Return-to-Origin Fraud Detection & Risk Scoring. Protects margins before shipping. | *LightGBM, SHAP, Twilio Connect* |
| **⏱️ ZenETA (F7)** | ETA Quantile Prediction. Accurate delivery estimates minimizing SLA breaches. | *XGBoost (p50/p90/p99 Quantiles)* |

### Advanced Intelligence Layer

| Module | Purpose & Function | Tech Stack / Models |
| :--- | :--- | :--- |
| **💡 Explainability (F8)** | Actionable Transparency & Counterfactual Reasoning. Translates "black box" decisions into insights. | *SHAP Heatmaps, Risk Matrices, Plotly JS* |
| **🔗 Blockchain (F9)** | Auditable Logistics Ledger. Decentralized, immutable logs for critical routing decisions. | *Polygon-compatible Web3.py, Merkle Trees* |
| **🌐 Synthesis (F10)** | Decentralized Agentic Control Loop. Orchestrates all models into a complex reasoning graph. | *LangGraph, Chat LLM State* |

---

## ✨ Core Features Highlights

1. **Intelligent Anomaly Detection:** Instantly flags shipment delays, route deviations, and capacity constraints using advanced Isolation Forests.
2. **Cascade Impact Analysis:** Maps out multi-tier contagion risk via DAG structures, ensuring you know exactly which shipments are at risk down the line.
3. **Autonomous Execution:** The platform doesn't just alert; it acts. The Actor Agent proactively swaps out failing carriers while maintaining strict SLAs.
4. **Predictive Analytics Foundation:** Extensive ML models trained on vast historical datasets predict congestion, precise ETAs, and RTO probabilities before they happen.
5. **AI Explainability (Glass-Box ML):** Operators get full transparency into *why* AI decisions are made using interactive SHAP heatmaps and waterfall charts.
6. **Web3 Audit Trails:** Every autonomous swap or reroute is anchored onto a blockchain ledger, ensuring cryptographic accountability and immutability.
7. **Minimalist UI:** A sleek, bright, and highly responsive dashboard engineered to present complex data layers naturally and intuitively.

---

## 🧩 Modular Standalone Projects

The LogiSense Unified Platform is a powerful integration of multiple specialized AI microservices. If you want to explore, study, or deploy these models individually, you can visit their standalone repositories:

* **[ZenETA — Dynamic ETA Prediction](https://github.com/kanhaiya-98/zeneta.git)**  
  Accurate delivery estimates minimizing SLA breaches using advanced XGBoost quantile regression (p50/p90/p99).
* **[ZenRTO — AI-Powered Risk Scoring & COD Fraud Detection](https://github.com/kanhaiya-98/zenrto.git)**  
  An advanced ML platform for Indian e-commerce that stops Return-to-Origin (RTO) and Cash-on-Delivery (COD) fraud before the order is shipped. Built with LightGBM, SHAP feature explanations, ResNet-50 for return damage classification, and Twilio WhatsApp for automated user confirmation.
* **[ZenDec — Decision Engine + E-Way Bill (F6)](https://github.com/kanhaiya-98/zendec.git)**  
  Multi-Objective TOPSIS + HITL (Human-in-the-Loop) + Automated GST Compliance. Intelligently balances cost, SLA requirements, and AQI/carbon impact metrics.

---

## 📂 Repository Structure

```text
LogiSense-AI-Unified-Platform/
├── backend/
│   ├── agents/             # Legacy Orchestrators (Observer, Reasoner, Actor)
│   ├── api/                # Unified FastAPI App (main.py router)
│   ├── features/           # Intelligence Models (Explainability, Blockchain, Synthesis)
│   ├── zen/                # The Zen Platform (Core algorithms, Demand, ETA, RTO modular routers)
│   ├── db/                 # Supabase ORM layer
│   └── streams/            # Redis real-time Pub/Sub queues
│
└── frontend/
    └── src/
        ├── App.jsx         # Unified Tabbed Dashboard Router
        ├── components/     # UI Components (Badges, Trees, Notifications, Map)
        └── index.css       # Tailwind Global Styling
```

---

## 🚀 Quick Start Guide

### 1. Prerequisites
Ensure you have the following installed on your machine:
* **Python 3.9+**
* **Node.js v18+**
* **Local Redis Server:** Required for realtime stream processing. Install via `homebrew`, native, or run `docker run -d -p 6379:6379 redis`.

### 2. Environment Configuration

**Backend:**
Navigate to the root directory and copy the backend example environment file:
```bash
cp backend/.env.example backend/.env
```
*Open `backend/.env` and insert your specific Supabase URL/Key and Gemini API Key.*

**Frontend:**
Navigate to the root directory and configure the frontend variables:
```bash
cp frontend/.env.example frontend/.env
```
*Open `frontend/.env` and ensure it maps to the FastAPI server (`VITE_API_URL=http://localhost:8000`).*

### 3. Database Initialization (Supabase)
To enable the full capabilities of the Zen Platform (ZenDec, ZenRTO, ZenETA) and other predictive features, you must create the necessary tables, functions, and seed data in your Supabase database:
1. Open your [Supabase Dashboard](https://supabase.com/dashboard).
2. Navigate to the **SQL Editor** and open a "New Query".
3. Copy and execute the contents of the following SQL scripts (located in `backend/scripts/`) in order:
    - `backend/scripts/add_f4_tables.sql` *(Observer/Actor Platform data)*
    - `backend/scripts/add_f6_tables.sql` *(ZenDec & E-Way Bill schema)*
    - `backend/scripts/add_eta_tables.sql` *(ZenETA schema & sample shipments)*
    - `backend/scripts/add_rto_tables.sql` *(ZenRTO & buyer profiles schema)*

### 4. Backend Setup & Launch
Open a terminal instance and initialize the Python backend:
```bash
cd backend
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# Export PYTHONPATH so feature modules resolve correctly and run the server
PYTHONPATH=. python3 -m uvicorn api.main:app --reload --port 8000
```
> **Tip:** API Documentation is auto-generated and live at: http://localhost:8000/docs

### 4. Frontend Setup & Launch
Open a **second** terminal instance for the React/Vite Dashboard:
```bash
cd frontend
npm install
npm run dev
```
> **View Dashboard:** Access the highly responsive UI at: http://localhost:5173

---

## 🤝 Contributing & License
Constructive contributions, bug reports, and feature requests are always welcome. 


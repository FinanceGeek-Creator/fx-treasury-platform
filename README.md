# Institutional FX Treasury & Structuring Platform

An enterprise-grade FX structuring and treasury risk analytics platform designed to model, price, and visualize complex FX derivatives and corporate hedging strategies.

## Overview
This platform empowers corporate treasurers and institutional sales desks to evaluate structured FX solutions, compute value-at-risk (VaR), and analyze counterparty credit risk (CVA/DVA) across major currency pairs.

## Key Features
* **FX Derivatives Pricing**: Interactive pricing engine for Vanilla Options, Zero-Cost Collars, Participators, and Knock-Out/Knock-In Structures.
* **Quantitative Risk Analytics**: Monte Carlo simulation engine for portfolio exposure path modeling.
* **Credit Value Adjustment (CVA)**: Integrated counterparty credit risk and bilateral margin analytics.
* **Institutional PDF Reporting**: Auto-generates client-ready term sheets and risk disclosure pitchbooks via ReportLab.
* **Containerized Deployment**: Fully Dockerized build configured for microservice architecture and web-based execution.

## Tech Stack
* **Core Language**: Python 3.10+
* **Frontend / Dashboard**: Streamlit, Plotly (Dynamic Charts)
* **Reporting Engine**: ReportLab (PDF Generation)
* **DevOps / Deployment**: Docker

## Quick Start (Docker)
```bash
# Build the Docker image
docker build -t fx-structuring-engine .

# Run the container locally on port 8504
docker run -p 8504:8501 fx-structuring-engine

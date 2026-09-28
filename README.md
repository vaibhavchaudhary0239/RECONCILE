# 🚀 RECONCILE - Ante-Mortem & Post-Mortem Reconcilation System

> ⚠️ **Replace everything in `[ ]` brackets with your actual content before submission.**

---

## 👥 Team

| Field | Value |
|---|---|
| **Team Name** | 404_Not_Found |
| **Track** | AI / Sustainability |
| **Team Lead** | Nimmi — nimmisoni14@gmail.com |
| **Members** | Anjali, Indrajit, Vaibhav |

---

## 🎯 Problem Statement

In a mass disaster, every unidentified victim represents a family waiting for answers. The identification process can become slow and overwhelming when large amounts of ante-mortem and post-mortem data must be manually cross-checked. Our project helps forensic and disaster-response teams rapidly find the most probable matches, reducing manual effort and supporting faster, more organized victim identification.

---

## 💡 Solution

RECONCILE is an AI-assisted Disaster Victim Identification system that helps investigators reconcile missing-person information with unidentified-body records. It extracts important details from natural-language or structured input, uses State-based searching and multi-factor similarity matching to find the top potential candidates, and presents the matching factors and differences for investigator verification. The system supports investigators in the identification process but does not automatically confirm a victim's identity.

---

## ✨ Key Features

- **Feature 1:** Natural-Language Information Extraction
- **Feature 2:** State-Based Search
- **Feature 3:** Multi-Factor DVI Matching
- **Feature 4:** Top 3 Explainable Candidates
- **Feature 5:** Role-Based Investigator & Admin Access

---

## 🛠️ Tech Stack

| Category | Technologies |
|---|---|
| **Languages** | Python |
| **Frameworks** | Streamlit |
| **Data Processing** | Pandas |
| **Database** | CSV |
| **AI / NLP** | Text Processing & Information Extraction |
| **Matching** | Weighted Similarity Matching |
| **Access Control** | Admin & Investigator Roles |
| **Deployment** | Local / Streamlit-based Application |

---

## 📁 Repository Structure

```
├── src/                  # All source code
├── docs/                 # Written documentation
│   ├── problem-statement.md
│   ├── solution-overview.md
│   ├── architecture.md
│   └── setup-guide.md
├── demo/                 # Demo artifacts
│   ├── screenshots/      # App screenshots
│   └── demo-video-link.txt  # Link to demo video
├── presentation/         # Slide deck
└── submission.yaml       # Structured submission metadata
```

---

## ⚡ How to Run

```bash
# 1. Clone the repository
git clone https://github.com/vaibhavchaudhary0239/RECONCILE.git
cd RECONCILE

# 2. Install dependencies
pip install -r src/requirements.txt

# 3. Configure environment
cp src/.env.example src/.env
# Edit src/.env if required

# 4. Run the Admin application
streamlit run src/dvi_admin_app.py

# OR run the Investigator application
streamlit run src/dvi_investigator_app.py
```

---

## 🖥️ Demo

| Artifact | Link |
|---|---|
| 📹 Demo Video | [See demo/demo-video-link.txt](demo/demo-video-link.txt) |
| 🌐 Live Demo | [See demo/live-demo-url.txt](demo/live-demo-url.txt) |
| 🖼️ Screenshots | [See demo/screenshots/](demo/screenshots/) |
| 📊 Presentation | [See presentation/slides.pdf](presentation/) |

---

## ⚠️ Known Limitations

- Synthetic DNA References: The DNA field contains synthetic reference IDs and does not perform actual DNA analysis.
- Prototype-Level Security: Real-world deployment would require stronger privacy protection, access control, forensic validation, and integration with authorized    forensic systems.
- Limited Scalability: The current prototype uses a CSV-based dataset, so very large datasets would require a more scalable database and optimized searching.

---

## 🏅 What We're Most Proud Of

We’re proud of building an end-to-end DVI workflow that turns natural-language information into structured attributes, searches and compares unidentified-body records, and produces explainable top-3 potential matches and keeping the system investigator-centric, with clear role separation, state-based search, and human verification rather than automated identity confirmation.

---

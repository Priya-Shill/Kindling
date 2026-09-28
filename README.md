# Kindling: Conversational Career Exploration Engine

Kindling is an AI-powered career guidance platform that mines behavioral communication signals from natural student dialogue to map user interests onto a 923-occupation career graph.

Unlike traditional static surveys that rely on self-reported preferences, Kindling evaluates *how* students communicate and what triggers their curiosity across 6 core dimensions.

---

## Team & Roles

* **Aleena (Data Engineering):** O*NET database pipeline processing and 923-occupation career graph clustering using Gaussian Mixture Models (GMM).
* **Sruthi (AI Core):** Resilient multi-provider LLM wrapper (`call_llm.py`) and 6-dimension behavioral scoring engine with prompt-injection defense (`reference.py`).
* **Priya (Backend Engineering):** RESTful Session API layer for state management, transcript handling, and chat history.
* **Gokul (Frontend & UI):** Interactive student dialogue interface designed and prototyped in Figma.

---

## Theoretical Foundations

Kindling's methodology is grounded in four core academic frameworks:

1. **Holland's Theory of Vocational Choice (RIASEC):** Maps personality types to occupational environments. Kindling's 6 dimensions align with Holland's Realistic, Investigative, Artistic, Social, Conventional, and Enterprising types.
2. **Krumboltz's Planned Happenstance Theory:** Recognizes that career paths emerge through dynamic curiosity rather than rigid tests.
3. **Samuelson's Revealed Preference Theory:** Evaluates actual observed choices and speech patterns rather than unreliable self-reported survey answers.
4. **Deci & Ryan's Self-Determination Theory (SDT):** Fosters student autonomy through open-ended dialogue rather than forced-choice questionnaires.

---

## The 6 Behavioral Dimensions

| Dimension | Description | Inspired RIASEC Category |
| :--- | :--- | :--- |
| `builds_tinkers` | Modifies, builds, or takes things apart; hands-on experimentation. | Realistic |
| `investigates_why` | Asks follow-up questions; seeks root-cause understanding. | Investigative |
| `creates_expresses` | Uses creative, artistic, or self-expressive language. | Artistic |
| `works_with_people` | Displays interest in helping, teaching, or connecting. | Social |
| `organizes_systems` | Seeks structure, order, planning, and categorization. | Conventional |
| `leads_persuades` | Displays initiative in leading, convincing, or influencing. | Enterprising |

---

## Tech Stack

* **AI & LLM:** Python, Groq API (`openai/gpt-oss-120b`), Google GenAI (`gemini-3.6-flash`), Few-Shot Prompt Engineering.
* **Data Science:** O*NET Database, Scikit-Learn (Gaussian Mixture Models), Pandas, NumPy.
* **Backend:** Python REST API, `python-dotenv`, custom JSON Schema Validators.
* **Frontend:** Figma UI/UX Prototypes.
## Setup

git clone https://github.com/Priya-on-loop/Kindling.git
cd Kindling
pip install -r requirements.txt

Create a `.env` file in the project root (never commit this, it's already covered by `.gitignore`) :

GROQ_API_KEY=your_key_here
GEMINI_API_KEY=your_key_here


## Team

Priya Shill, Sruthi G S, Gokul V S, Aleena Philip Shaji

## Project tracking

Jira dashboard (status overview + Review 1 progress) : https://priyainloop.atlassian.net/jira/dashboards/10003

Jira backlog (full sprint board, all issues) : https://priyainloop.atlassian.net/jira/software/projects/TCP/boards/4/backlog

Deployed Link : https://priya-on-loop.github.io/Kindling/frontend/

## License

MIT License

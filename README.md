# NidhiFlow 🌱
### Making every saving count.

**A Malayalam-first, voice-assisted digital passbook for Self-Help Groups (SHGs).**

NidhiFlow aims to make financial record-keeping more accessible, transparent, and understandable for community-based Self-Help Groups, especially Kudumbashree members.

By combining voice technology with digital record management, NidhiFlow explores how everyday financial transactions can be recorded and verified more easily, even for users who are more comfortable communicating in Malayalam than navigating complex digital interfaces.

---

## 🚩 The Problem

Many Self-Help Groups rely on manual records and traditional bookkeeping methods. These processes can create challenges such as:

- Difficulty maintaining consistent financial records.
- Language and digital-literacy barriers.
- Time-consuming transaction entry and verification.
- Limited transparency when checking previous records.

NidhiFlow explores a more accessible way to manage these records through voice interaction and digital verification.

## 💡 Our Solution

NidhiFlow is a voice-assisted digital passbook concept designed around the needs of SHG members.

The prototype brings together:

- **Voice Interaction:** Uses Gnani.ai speech technology to support voice-based input.
- **Malayalam Accessibility:** Designed with Malayalam-speaking users in mind.
- **Transaction Confirmation:** Supports a human confirmation step before accepting transaction details.
- **Digital Record Management:** Uses a database-backed approach to maintain records.
- **Tamper Detection:** Explores SHA-256 hash-linked records to help identify changes to stored ledger data.
- **Accountability:** Incorporates verification and governance checks into the proposed workflow.

## ⚙️ How It Works

1. A user provides transaction information through voice input.
2. Speech recognition converts the audio into text.
3. The transaction details can be reviewed and confirmed by the user.
4. The application processes the confirmed information.
5. Records are stored in the database.
6. Hash-based verification helps identify unexpected changes to linked records.

**Human confirmation is an important part of the workflow:** speech recognition output should be reviewed rather than automatically treated as a verified financial transaction.

## 🛠️ Technology Stack

| Component | Technology |
|---|---|
| Programming Language | Python |
| User Interface | Streamlit |
| Speech Technology | Gnani.ai |
| Database | SQLite |
| Data Integrity | SHA-256 |
| Development Environment | Antigravity IDE |

## 🏗️ Project Structure

```text
nidhi_flow/
│
├── app.py
├── core/
├── audio/
├── tests/
├── requirements.txt
├── README.md
└── .gitignore
```

*The structure above highlights the main project components; additional files may be present in the repository.*

## 🚀 Getting Started

### Prerequisites

- Python 3.x
- pip
- Gnani.ai API access and the required credentials

### Installation

1. Clone the repository:

```bash
git clone https://github.com/nessamarysunil/nidhi_flow.git
```

2. Navigate to the project directory:

```bash
cd nidhi_flow
```

3. Install dependencies:

```bash
pip install -r requirements.txt
```

4. Configure the required environment variables and API credentials locally. Do not upload secrets or `.env` files to GitHub.

5. Start the application:

```bash
streamlit run app.py
```

## 🔐 Security and Transparency

NidhiFlow explores the use of:

- SHA-256 hashing for data-integrity verification.
- Human review and confirmation of recognized transaction details.
- Database-backed record management.
- Verification checks within the transaction workflow.

These mechanisms are intended to improve transparency. They should not be interpreted as a guarantee that the prototype is production-ready or that all financial records are independently audited.

## 🌍 Our Vision

We envision a future where technology makes financial management simpler and more accessible for every community.

NidhiFlow aims to bridge the gap between traditional community savings practices and accessible digital tools—while keeping transparency, usability, and human trust at the centre.

**Making every saving count.**

---

## 👥 Team

Built by a team of two as part of the Gnani.ai challenge.

## 📌 Project Status

**Prototype / Hackathon Project**

NidhiFlow is an ongoing prototype. Features and workflows may evolve as development and testing continue.

## 📄 License

See the repository's `LICENSE` file for licensing information.

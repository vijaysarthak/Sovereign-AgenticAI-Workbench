# SEVERANCE API Documentation

All endpoints (except `/auth/login`) authenticate callers via an `HttpOnly` signed session cookie (`severance_session`).
**The identity of the caller is derived strictly from the verified session cookie and the user store.**
There are no query parameters or request body fields allowing a caller to claim a grade or compartment.

---

## 1. Authentication Endpoints

### `POST /auth/login`
Authenticates a user with `person_id` and `password`. On success, sets an `HttpOnly`, `SameSite=Lax` cookie named `severance_session`.

**Request Body:**
```json
{
  "person_id": "cvo-001",
  "password": "Password123!"
}
```

**Response (200 OK):**
```json
{
  "status": "success",
  "principal": {
    "person_id": "cvo-001",
    "name": "Chief Vigilance Officer",
    "job_title": "CVO",
    "grade": "G",
    "compartments": ["vigilance"],
    "is_admin": false
  },
  "must_change_password": false
}
```

**Errors:**
- `401 Unauthorized`: Invalid credentials or deactivated account.

---

### `POST /auth/logout`
Terminates the active session and clears the `severance_session` cookie.

**Response (200 OK):**
```json
{
  "status": "logged_out"
}
```

---

### `POST /auth/change-password`
Changes the authenticated caller's password. Mandatory when `must_change_password` is true.

**Request Body:**
```json
{
  "old_password": "InitialTemporaryPassword123!",
  "new_password": "NewSecurePassword456!"
}
```

**Response (200 OK):**
```json
{
  "status": "password_updated"
}
```

**Errors:**
- `400 Bad Request`: Incorrect current password or new password shorter than 8 characters.
- `401 Unauthorized`: Unauthenticated session.

---

### `GET /me`
Returns the currently authenticated `Principal` profile.

**Response (200 OK):**
```json
{
  "person_id": "eng-101",
  "name": "Ramesh Rao",
  "job_title": "Senior Process Engineer",
  "grade": "C",
  "compartments": ["technical", "hse"],
  "is_admin": false
}
```

---

## 2. Administration Endpoints (Admin Role Only)

*Admins can create accounts and assign hierarchical pay grades. Admins CANNOT grant compartments.*

### `POST /admin/users`
Provisions a new employee account. Generates a temporary password returned once in the response.

**Request Body:**
```json
{
  "person_id": "safety-002",
  "name": "Priya Sharma",
  "job_title": "Safety Officer",
  "grade": "B"
}
```

**Response (201 Created):**
```json
{
  "user": {
    "person_id": "safety-002",
    "name": "Priya Sharma",
    "job_title": "Safety Officer",
    "grade": "B",
    "compartments": [],
    "is_admin": false,
    "is_active": true,
    "must_change_password": true
  },
  "temporary_password": "temp-a8f9c2d1e0b3"
}
```

**Errors:**
- `400 Bad Request`: Invalid MRPL grade or person_id already exists.
- `403 Forbidden`: Caller is not an administrator.

---

### `GET /admin/users`
Lists all provisioned accounts.

**Response (200 OK):**
```json
[
  {
    "person_id": "admin-001",
    "name": "System Administrator",
    "job_title": "HR Systems Admin",
    "grade": "E",
    "compartments": [],
    "is_admin": true,
    "is_active": true,
    "must_change_password": false
  },
  {
    "person_id": "safety-002",
    "name": "Priya Sharma",
    "job_title": "Safety Officer",
    "grade": "B",
    "compartments": ["hse"],
    "is_admin": false,
    "is_active": true,
    "must_change_password": true
  }
]
```

---

### `PATCH /admin/users/{id}/grade`
Modifies an employee's MRPL pay grade.
**Rule:** An admin CANNOT modify their own grade. Another admin is required.

**Request Body:**
```json
{
  "grade": "C"
}
```

**Response (200 OK):**
```json
{
  "status": "grade_updated",
  "person_id": "safety-002",
  "old_grade": "B",
  "new_grade": "C"
}
```

**Errors:**
- `400 Bad Request`: Invalid MRPL grade or user not found.
- `403 Forbidden`: Caller attempting self-modification (`Cannot modify own grade`) or caller not admin.

---

### `POST /admin/users/{id}/deactivate`
Deactivates an employee account (sets `is_active=False`). User record remains in database to preserve audit integrity.

**Response (200 OK):**
```json
{
  "status": "user_deactivated",
  "person_id": "safety-002"
}
```

**Errors:**
- `403 Forbidden`: Caller attempting self-deactivation or caller not admin.

---

## 3. Compartment Grant Endpoints (Sponsors Only)

*Compartments are granted exclusively by the compartment's designated sponsor in `config/compartments.json`. Admins cannot grant compartments.*

### `POST /grants`
Grants a compartment to an employee.
**Rules:**
1. Caller must be the registered sponsor of that specific compartment (or an authorized delegate).
2. A sponsor CANNOT grant a compartment to themselves.

**Request Body:**
```json
{
  "person_id": "safety-002",
  "compartment": "hse"
}
```

**Response (200 OK):**
```json
{
  "status": "compartment_granted",
  "actor": "safety-001",
  "subject": "safety-002",
  "compartment": "hse"
}
```

**Errors:**
- `403 Forbidden`: Caller does not sponsor this compartment, or caller attempted self-grant.
- `404 Not Found`: Target person_id does not exist.

---

### `DELETE /grants`
Revokes a compartment from an employee.
**Rules:** Same as grant — sponsor of that compartment only; cannot modify own compartments.

**Request Body:**
```json
{
  "person_id": "safety-002",
  "compartment": "hse"
}
```

**Response (200 OK):**
```json
{
  "status": "compartment_revoked",
  "actor": "safety-001",
  "subject": "safety-002",
  "compartment": "hse"
}
```

---

### `GET /grants/mine`
Returns the list of compartments that the authenticated caller has the authority to grant or revoke.

**Response (200 OK):**
```json
{
  "sponsored_compartments": ["vigilance"]
}
```

---

## 4. Document Workbench Endpoints

### `POST /ask`
Primary query endpoint. Executes two-pass retrieval, deterministic two-axis security gating, immediate abstention if no readable matches exist, agent drafting, verbatim citation verification, classification inheritance, and cryptographic audit logging.

**Request Body:**
```json
{
  "question": "What are the emergency shutdown protocols for Crude Distillation Unit 2?",
  "top_k": 3
}
```

**Response (200 OK - Answered):**
```json
{
  "status": "answered",
  "answer": "Emergency shutdown of CDU-2 requires immediate actuation of ESD valve 201-XV-01 followed by nitrogen purging of column bottoms within 90 seconds.",
  "citations": [
    {
      "doc_id": "mrpl-sop-cdu2",
      "page": 14,
      "quote": "actuation of ESD valve 201-XV-01 followed by nitrogen purging of column bottoms within 90 seconds"
    }
  ],
  "denials": [
    {
      "doc_id": "mrpl-vigilance-procurement-audit",
      "reason": "Missing required compartment(s): vigilance",
      "required_label": {
        "tier": "confidential",
        "compartments": ["vigilance"]
      }
    }
  ],
  "effective_label": {
    "tier": "confidential",
    "compartments": ["technical"]
  },
  "ledger_row_id": 42
}
```

**Response (200 OK - Abstained):**
```json
{
  "status": "abstained",
  "answer": "Access denied: The requested information requires clearance for document 'mrpl-vigilance-procurement-audit' which is restricted under compartment 'vigilance'. No readable passages matched your query.",
  "citations": [],
  "denials": [
    {
      "doc_id": "mrpl-vigilance-procurement-audit",
      "reason": "Missing required compartment(s): vigilance",
      "required_label": {
        "tier": "confidential",
        "compartments": ["vigilance"]
      }
    }
  ],
  "effective_label": {
    "tier": "public",
    "compartments": []
  },
  "ledger_row_id": 43
}
```

---

### `GET /documents`
Lists all documents in the corpus along with a per-user `readable` boolean flag evaluated against the authenticated caller's grade and compartments.

**Response (200 OK):**
```json
[
  {
    "doc_id": "mrpl-sop-cdu2",
    "title": "Standard Operating Procedure: CDU-2 Operations",
    "source": "MRPL Refining Operations Manual 2024",
    "label": {
      "tier": "confidential",
      "compartments": ["technical"]
    },
    "readable": true,
    "denial_reason": null
  },
  {
    "doc_id": "mrpl-vigilance-audit",
    "title": "Quarterly Vigilance Inspection Report Q3 2025",
    "source": "MRPL Chief Vigilance Officer Disclosures",
    "label": {
      "tier": "confidential",
      "compartments": ["vigilance"]
    },
    "readable": false,
    "denial_reason": "Missing required compartment(s): vigilance"
  }
]
```

---

### `GET /ledger`
Retrieves recent audit entries from the hash-chained SQLite ledger.

**Query Parameters:**
- `limit` (optional integer, default 50)

**Response (200 OK):**
```json
[
  {
    "row_id": 1,
    "timestamp": "2026-09-14T10:00:00Z",
    "actor": "system_bootstrap",
    "action": "BOOTSTRAP_ADMIN",
    "details": {"admin_id": "admin-001"},
    "prev_hash": "0000000000000000000000000000000000000000000000000000000000000000",
    "hash": "7f83b1657ff1fc53b92dc18148a1d65dfc2d4b1fa3d677284addd200126d9069"
  }
]
```

---

### `GET /ledger/verify`
Performs cryptographic verification across every entry in the audit ledger:
1. Recomputes SHA-256 for every entry using canonical JSON serialization.
2. Confirms that row `i`'s `prev_hash` equals row `i-1`'s `hash`.

**Response (200 OK - Chain Intact):**
```json
{
  "intact": true,
  "total_rows": 142,
  "broken_at_row_id": null
}
```

**Response (200 OK - Chain Compromised):**
```json
{
  "intact": false,
  "total_rows": 142,
  "broken_at_row_id": 40
}
```

---

### `GET /report/{ledger_row_id}`
Downloads a formatted `.docx` Word report corresponding to an answered `/ask` query recorded at `ledger_row_id`.
The report contains **3-way classification stamping**:
1. Prominent banner paragraph at the top of page 1.
2. Running header and footer on every page.
3. Filename stamped with classification tier (e.g. `SEVERANCE_Report_Row42_CONFIDENTIAL.docx`).

**Response (200 OK):**
Binary `application/vnd.openxmlformats-officedocument.wordprocessingml.document` stream with `Content-Disposition` attachment header.

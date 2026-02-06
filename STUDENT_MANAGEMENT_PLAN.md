# Plan: Restructuring Student Management (Class-Centric Workflow)

## Objective
Transform the "Students" section from a flat list into a **Class-Based Management Hub**. This mirrors the real-world school structure where activities revolve around physical classes (Primary 1, JHS 2, etc.).

## 1. New "Classes & Students" Dashboard
Instead of seeing a long list of 500 students immediately, users (Admin & Teachers) will see a **Class Grid**.
- **Visuals:** Cards for each level (Primary 1 - JHS 3).
- **Info:** Each card shows "Total Students", "Class Teacher" (optional).
- **Action:** Clicking a card opens the **Class Workspace**.

## 2. The "Class Workspace" (Level Detail View)
A dedicated page for a specific class (e.g., **Primary 4 Management**).

### Sections within the Workspace:
*   **A. Student Roster (The Register)**
    *   List of all students in this class.
    *   **Head Master/Admin Only:** Button to **"Add New Student"** (Automatically sets the Level to Primary 4).
*   **B. Academic Records (Results)**
    *   **Teachers:** Easy access to "Enter Scores" for subjects in this class.
    *   **View Broadsheet:** A summary table showing all student grades for the term side-by-side.
    *   **Upload Results:** Bulk upload interaction.
*   **C. Promotion Console (Third Term Only)**
    *   Only visible in Third Term.
    *   Visible to **Class Teachers** and **Head Masters**.
    *   Button: **"Promote Class"**. Automated wizard to move passing students to the next level (e.g., Primary 4 -> Primary 5).

## 3. Workflow Permissions
*   **Head Master (Admin):**
    *   Full Access.
    *   Exclusive right to **Add/Register new students**.
    *   Can oversee all classes.
*   **Teachers:**
    *   Can view Student Rosters.
    *   Can Enter Scores/Results.
    *   Can **Promote** students (in 3rd Term).
    *   *Cannot* delete or register new students (read/update only).
*   **Students:**
    *   Login restricts them to their own portal.
    *   Can only view **published results** (we will ensure a "Result Release" toggle exists or rely on the generation of the Report Card).

## 4. Implementation Steps
1.  **Create `class_list_view`:** The entry point showing the grid of levels.
2.  **Create `class_detail_view`:** The workspace URL (e.g., `/students/primary-1/`).
3.  **Update `StudentAddForm`:** Ensure it can accept a pre-filled `level` from the URL so Admins don't have to select it manually.
4.  **Enhance `Promotion View`:** Allow Teachers to access it, scoped to the specific class they are viewing.

---
**Shall I proceed with Phase 1: Creating the "Classes Dashboard" and the "Class Workspace"?**

# Multi-Tenant SaaS Architecture Diagram

```
┌─────────────────────────────────────────────────────────────────────────┐
│                         SAAS SCHOOL MANAGEMENT SYSTEM                    │
└─────────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────────┐
│                           ACCESS LAYERS                                  │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                          │
│  ┌──────────────────┐  ┌──────────────────┐  ┌──────────────────┐     │
│  │  SUPER ADMIN     │  │  SCHOOL ADMIN    │  │  TEACHERS/       │     │
│  │  (is_superuser)  │  │ (is_school_admin)│  │  STUDENTS        │     │
│  │                  │  │                  │  │                  │     │
│  │  • Manages ALL   │  │  • ONE school    │  │  • School        │     │
│  │    schools       │  │  • Create users  │  │    resources     │     │
│  │  • Creates       │  │  • Manage data   │  │  • Role-based    │     │
│  │    admins        │  │  • School scope  │  │    permissions   │     │
│  │  • /superadmin/  │  │  • /programs/    │  │  • Read-only     │     │
│  │                  │  │    /result/      │  │    mostly        │     │
│  └──────────────────┘  └──────────────────┘  └──────────────────┘     │
│           │                     │                      │                │
└───────────┼─────────────────────┼──────────────────────┼───────────────┘
            │                     │                      │
            ▼                     ▼                      ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                       SCHOOL MIDDLEWARE                                  │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                          │
│  1. Detect School                                                       │
│     ├─ Subdomain (greenwood.yourdomain.com)                            │
│     ├─ User's Assigned School                                          │
│     └─ Session (fallback)                                              │
│                                                                          │
│  2. Enforce Isolation                                                   │
│     ├─ User.school == Request.school ✓                                 │
│     ├─ Superusers bypass all checks                                    │
│     └─ Block cross-school access ✘                                     │
│                                                                          │
│  3. Attach to Request                                                   │
│     └─ request.school available in all views                           │
│                                                                          │
└─────────────────────────────────────────────────────────────────────────┘
            │
            ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                           DATABASE LAYER                                 │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                          │
│  ┌────────────────────────────────────────────────────────────────┐   │
│  │                         SCHOOL                                  │   │
│  │  • id, name, subdomain, slug                                   │   │
│  │  • logo, primary_color, secondary_color                        │   │
│  │  • is_active, created_at                                       │   │
│  └────────────────────────────────────────────────────────────────┘   │
│           │                                                             │
│           │ (1:N)                                                       │
│           ▼                                                             │
│  ┌────────────────────────────────────────────────────────────────┐   │
│  │                          USER                                   │   │
│  │  • username, email, password                                   │   │
│  │  • school (ForeignKey)                                         │   │
│  │  • is_superuser, is_school_admin                              │   │
│  │  • is_student, is_lecturer                                    │   │
│  └────────────────────────────────────────────────────────────────┘   │
│           │                                                             │
│           │ (1:N)                                                       │
│           ▼                                                             │
│  ┌─────────┬─────────┬──────────┬──────────┬──────────┬────────┐     │
│  │ Student │ Course  │  Result  │ Quiz     │ Payment  │ ...    │     │
│  │         │         │          │          │          │        │     │
│  │ school  │ school  │  school  │  school  │  school  │ school │     │
│  │   FK    │   FK    │    FK    │    FK    │    FK    │   FK   │     │
│  └─────────┴─────────┴──────────┴──────────┴──────────┴────────┘     │
│                                                                          │
│  ALL models have school ForeignKey for complete isolation              │
│                                                                          │
└─────────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────────┐
│                         URL ROUTING                                      │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                          │
│  /superadmin/                  → Super Admin Portal                     │
│  /superadmin/schools/          → List Schools                           │
│  /superadmin/schools/create/   → Create School + Admin                  │
│  /superadmin/schools/<id>/     → School Details                         │
│                                                                          │
│  /                             → Dashboard (school filtered)            │
│  /programs/                    → Courses (school filtered)              │
│  /result/                      → Results (school filtered)              │
│  /timetable/                   → Timetables (school filtered)           │
│  /accounts/                    → Users (school filtered)                │
│                                                                          │
└─────────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────────┐
│                      DATA FLOW EXAMPLE                                   │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                          │
│  1. Super Admin creates "Greenwood Academy"                            │
│     └─ POST /superadmin/schools/create/                                │
│        ├─ School created (subdomain: greenwood)                        │
│        └─ Admin created (greenwood_admin)                              │
│                                                                          │
│  2. greenwood_admin logs in                                            │
│     └─ Middleware detects:                                             │
│        └─ user.school = Greenwood Academy                              │
│                                                                          │
│  3. Admin creates student                                              │
│     └─ POST /accounts/student/add/                                     │
│        └─ Student.school = Greenwood Academy (automatic)               │
│                                                                          │
│  4. Admin views students                                               │
│     └─ GET /accounts/students/                                         │
│        └─ Query: Student.objects.filter(school=request.school)         │
│           └─ Returns ONLY Greenwood students ✓                         │
│                                                                          │
│  5. greenwood_admin tries to access Riverside data                     │
│     └─ Middleware blocks:                                              │
│        ├─ user.school = Greenwood                                      │
│        ├─ detected school = Riverside                                  │
│        └─ Access DENIED ✘                                              │
│                                                                          │
└─────────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────────┐
│                      SUBDOMAIN ROUTING (Production)                      │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                          │
│  DNS: *.yourdomain.com → Server IP                                     │
│                                                                          │
│  greenwood.yourdomain.com                                              │
│     └─ Middleware extracts: subdomain = "greenwood"                    │
│        └─ School.objects.get(subdomain="greenwood")                    │
│           └─ request.school = Greenwood Academy                        │
│                                                                          │
│  riverside.yourdomain.com                                              │
│     └─ Middleware extracts: subdomain = "riverside"                    │
│        └─ School.objects.get(subdomain="riverside")                    │
│           └─ request.school = Riverside School                         │
│                                                                          │
│  yourdomain.com/superadmin/                                            │
│     └─ No subdomain, superuser access                                  │
│        └─ Full system access                                           │
│                                                                          │
└─────────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────────┐
│                      SECURITY GUARANTEES                                 │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                          │
│  ✓ School A CANNOT see School B's data                                 │
│  ✓ School A admin CANNOT become School B admin                         │
│  ✓ All queries automatically filtered by school                        │
│  ✓ Middleware enforces boundaries at HTTP layer                        │
│  ✓ Database constraints prevent orphaned data                          │
│  ✓ Superusers have God-mode for management only                        │
│  ✓ Atomic transactions ensure data consistency                         │
│  ✓ Form validation prevents subdomain conflicts                        │
│                                                                          │
└─────────────────────────────────────────────────────────────────────────┘
```

## Key Concepts

### 1. **Multi-Tenancy Pattern**
- **Shared Database, Isolated Data** - One database, filtered by `school_id`
- **Row-Level Security** - Every model has `school` ForeignKey
- **Middleware Enforcement** - HTTP-layer access control

### 2. **School Detection Priority**
1. Subdomain (`greenwood.yourdomain.com`)
2. User's School (`user.school`)
3. Session (`request.session['school_slug']`)
4. First School (fallback)

### 3. **Access Control**
- **Superuser**: Bypass all school restrictions
- **School Admin**: Bound to one school, full school management
- **Users**: Bound to school, role-based permissions

### 4. **Data Flow**
Every database query automatically includes:
```python
Model.objects.filter(school=request.school)
```

No manual filtering needed - middleware provides `request.school`!

# Multi-Tenant SaaS School Management System

## 🎯 Overview

This application is now a fully functional multi-tenant SaaS platform where:
- A **Super Admin** can create and manage multiple schools
- Each school operates in complete isolation
- Schools cannot see or access each other's data
- Each school has its own administrators

## 🏗️ Architecture

### 1. **Data Isolation**
- Every model includes a `school` foreign key
- Enhanced `SchoolMiddleware` enforces school boundaries
- Users can only access data from their assigned school
- Superusers bypass all restrictions for management

### 2. **Access Levels**

#### Super Admin (is_superuser=True)
- Can access `/superadmin/` portal
- Creates and manages all schools
- Assigns school administrators
- Views across all schools
- No school restrictions

#### School Admin (is_school_admin=True)
- Manages their assigned school only
- Creates students, teachers, courses
- Views only their school's data
- Cannot access other schools

#### Teachers/Students
- Access only their school's resources
- Limited by role-based permissions
- Completely isolated from other schools

### 3. **School Detection**

The system detects the current school in this priority order:
1. **Subdomain** - `schoolname.yourdomain.com` (ideal for production)
2. **User's School** - Authenticated user's assigned school
3. **Session** - `school_slug` in session (for testing)
4. **Fallback** - First school in database

## 🚀 Getting Started

### Initial Setup

1. **Create migrations** (if not already done):
```bash
./venv/bin/python manage.py makemigrations
./venv/bin/python manage.py migrate
```

2. **Create a superuser**:
```bash
./venv/bin/python manage.py createsuperuser
```

3. **Access the Super Admin portal**:
```
http://localhost:8000/superadmin/
```

4. **Create your first school**:
   - Click "Create New School"
   - Fill in school details (name, subdomain, etc.)
   - Create the school administrator
   - The admin will be able to log in and manage their school

### Creating Schools

1. Log in as superuser
2. Navigate to `/superadmin/`
3. Click "Create New School"
4. Fill in:
   - **Name**: School name
   - **Subdomain**: Unique subdomain (e.g., `greenwood`)
   - **Admin Details**: Username, email, password for school admin
5. Submit - The school and admin are created atomically

### Subdomain Setup (Production)

For true multi-tenancy, configure your domain:

1. **DNS Wildcard Record**:
```
*.yourdomain.com → Your Server IP
```

2. **Update `ALLOWED_HOSTS` in settings.py**:
```python
ALLOWED_HOSTS = ['yourdomain.com', '*.yourdomain.com', 'localhost', '127.0.0.1']
```

3. **Schools are accessible at**:
- `greenwood.yourdomain.com` → Greenwood School
- `riverside.yourdomain.com` → Riverside School

## 📁 Key Files

### New Files Created
- `superadmin/` - Super Admin application
  - `views.py` - School and admin management views
  - `forms.py` - School creation and admin forms
  - `urls.py` - Super admin routes
  - `templates/superadmin/` - Super admin templates

### Modified Files
- `school/middleware.py` - Enhanced multi-tenant enforcement
- `config/settings.py` - Added superadmin app
- `config/urls.py` - Added superadmin routes

## 🔒 Security Features

1. **School Isolation**: Users cannot access other schools' data
2. **Middleware Enforcement**: Every request validates school access
3. **Admin Separation**: School admins can't become superusers
4. **Data Validation**: Forms validate subdomain uniqueness
5. **Session Protection**: School switching prevented for non-superusers

## 📊 Database Schema

### School Model
- `name` - School name
- `subdomain` - Unique subdomain
- `slug` - URL-safe identifier
- `is_active` - Enable/disable school
- `logo`, `primary_color`, `secondary_color` - Branding
- `created_at`, `updated_at` - Timestamps

### User Model (Enhanced)
- `is_school_admin` - School administrator flag
- `school` - Foreign key to School
- Existing: `is_student`, `is_lecturer`, etc.

## 🎨 URLs Structure

### Super Admin Portal
- `/superadmin/` - Dashboard
- `/superadmin/schools/` - School list
- `/superadmin/schools/create/` - Create school
- `/superadmin/schools/<id>/` - School details
- `/superadmin/schools/<id>/edit/` - Edit school
- `/superadmin/schools/<id>/toggle-active/` - Activate/deactivate
- `/superadmin/schools/<id>/add-admin/` - Add admin to school

### Main Application
- `/` - School dashboard (filtered by school)
- `/accounts/` - Account management
- `/programs/` - Course programs
- `/result/` - Student results
- All existing routes work with school filtering

## 🧪 Testing Multi-Tenancy

### Method 1: Session-based (Development)
```python
# In Django shell or test
request.session['school_slug'] = 'greenwood'
```

### Method 2: Subdomain (Production-like)
Edit `/etc/hosts`:
```
127.0.0.1 greenwood.localhost
127.0.0.1 riverside.localhost
```

Access: `http://greenwood.localhost:8000`

### Method 3: User-based
- Log in as different school users
- Each sees only their school's data

## 📝 Usage Examples

### Creating a Second School
```bash
# As superuser in /superadmin/
1. Create School: "Riverside Academy"
2. Subdomain: "riverside"
3. Admin: username="riverside_admin", email="admin@riverside.com"
4. Submit
```

### Adding More Admins to a School
```bash
# As superuser in /superadmin/schools/<school_id>/
1. Click "Add Admin"
2. Fill in admin detailsscript
3. Submit - New admin can manage same school
```

### School Admin Workflow
```bash
1. Log in as school admin
2. Automatically sees only their school
3. Can create students, teachers, courses
4. Cannot switch to other schools
5. Cannot access superadmin portal
```

## 🔧 Customization

### Branding Per School
Each school can have:
- Custom logo (`school.logo`)
- Primary color (``school.primary_color`)
- Secondary color (`school.secondary_color`)

Use in templates:
```html
{% if current_school %}
<style>
    :root {
        --primary-color: {{ current_school.primary_color }};
        --secondary-color: {{ current_school.secondary_color }};
    }
</style>
{% endif %}
```

### Reserved Subdomains
The following subdomains are reserved and cannot be used:
- `www`, `admin`, `superadmin`, `api`, `mail`, `ftp`, `localhost`

Add more in `superadmin/forms.py`:
```python
reserved = ['www', 'admin', 'superadmin', ...your subdomains...]
```

## ⚠️ Important Notes

1. **First Time Setup**: Create superuser before accessing `/superadmin/`
2. **Production**: Use subdomain-based routing with wildcard DNS
3. **Middleware Order**: `SchoolMiddleware` must be after `AuthenticationMiddleware`
4. **School Required**: Most views require `request.school` to be set
5. **Database**: Each school shares the same database but data is isolated

## 🐛 Troubleshooting

### "No school found"
- Ensure at least one school exists
- Check if user has `school` assigned
- Verify subdomain in URL matches database

### "Cannot access this school"
- User trying to access wrong school
- Check `user.school` matches `request.school`
- Superusers bypass this check

### Admin can't create students
- Verify `is_school_admin=True`
- Check if user's school is active (`is_active=True`)
- Ensure school exists and is assigned

## 📈 Next Steps

1. ✅ Super Admin Portal - Complete
2. ✅ School Isolation - Complete
3. ✅ Multi-tenant Middleware - Complete
4. 🔄 Custom Domains (Optional)
5. 🔄 Billing Integration (Optional)
6. 🔄 School Analytics Dashboard (Optional)

## 📞 Support

For issues or questions:
1. Check this README
2. Review middleware logic in `school/middleware.py`
3. Inspect school detection in `school/utils.py`
4. Check superadmin views in `superadmin/views.py`

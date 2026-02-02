from django.conf import settings
from django.utils.deprecation import MiddlewareMixin

class DomainRoutingMiddleware(MiddlewareMixin):
    """
    Middleware to route requests to different URL configurations based on the domain.
    
    - Admin Domain (e.g. admin.localhost) -> connects to Super Admin Portal
    - School Domains (e.g. greenwood.localhost) -> connects to School SaaS App
    """
    
    def process_request(self, request):
        host = request.get_host().split(':')[0].lower() # Remove port
        
        # Define your Master/Admin domains here
        # In production, this would be ['admin.yoursite.com', 'portal.yoursite.com']
        # For local testing: 
        # 127.0.0.1 -> Master Console 
        # localhost -> School App
        admin_domains = ['admin.localhost', 'master.localhost', '127.0.0.1']
        
        if host in admin_domains:
            # Load the Master/Super Admin configuration
            request.urlconf = 'config.urls_master'
        else:
            # Load the Public/School SaaS configuration
            # This configuration strictly DOES NOT have /superadmin/ URL patterns
            request.urlconf = 'config.urls_public'
            
        return None

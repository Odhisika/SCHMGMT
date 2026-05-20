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
        
        public_domains = getattr(settings, 'PUBLIC_DOMAINS', ['localhost'])
        admin_domains = getattr(settings, 'MASTER_DOMAINS', ['admin.localhost', 'master.localhost', '127.0.0.1'])
        
        # Public domains take precedence so the hosted school portal
        # never gets accidentally routed to the superadmin console.
        if host in public_domains:
            request.urlconf = 'config.urls_public'
        elif host in admin_domains:
            # Load the Master/Super Admin configuration
            request.urlconf = 'config.urls_master'
        else:
            # Load the Public/School SaaS configuration
            # This configuration strictly DOES NOT have /superadmin/ URL patterns
            request.urlconf = 'config.urls_public'
            
        return None

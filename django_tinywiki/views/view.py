from django.views import View
from django.urls import reverse
from .. import settings
from django.contrib.auth.models import Group
from django.utils.http import urlsafe_base64_encode
from .. import functions
from ..models.wiki import WikiPage
from django.utils.module_loading import import_string

class ViewBase(View):
    base_template = settings.TINYWIKI_BASE_TEMPLATE
    header_title = settings.TINYWIKI_TITLE
    css = settings.TINYWIKI_CSS
    context_callback = settings.TINYWIKI_CONTEXT_CALLBACK
    home_url = settings.TINYWIKI_HOME_URL
    page_view_url = settings.TINYWIKI_PAGE_VIEW_URL_TEMPLATE
    page_edit_url = settings.TINYWIKI_PAGE_EDIT_URL
    page_create_url = settings.TINYWIKI_PAGE_CREATE_URL_TEMPLATE
    page_new_url = settings.TINYWIKI_PAGE_NEW_URL_TEMPLATE
    page_delete_url = settings.TINYWIKI_PAGE_DELETE_URL_TEMPLATE
    login_url = settings.TINYWIKI_LOGIN_URL
    logout_url = settings.TINYWIKI_LOGOUT_URL
    signup_url = settings.TINYWIKI_SIGNUP_URL
    overview_url = settings.TINYWIKI_PAGE_OVERVIEW_URL
    index_url = settings.TINYWIKI_INDEX

    def get_user_can_create_pages(self,user):
        if user.is_authenticated:
            if user.is_superuser:
                return True

            required_groups = ['wiki-admin','wiki-author']
            for check_group in Group.objects.all():
                if check_group.name in required_groups:
                    return True

        return False

    def get_user_is_wiki_admin(self,user):
        if user.is_authenticated:
            if user.is_superuser:
                return True
            return bool(user.groups.filter(name='wiki-admin'))
        return False
            
    def get_user_can_edit_page(self,user,page=None):
        if page is None:
            return False
        
        return functions.auth.user_can_edit_page(user,page)

    def get_user_can_delete_page(self,user,page=None):
        if not user.is_authenticated:
            return False
        if not page:
            return False        
        return functions.auth.user_can_delete_pages(user)

    def get_context(self,request,page=None,login_url=None,**kwargs):
        if page is None:
            p = None
        elif isinstance(page,str):
            try:
                p = WikiPage.objects.get(slug=page)
            except WikiPage.DoesNotExist:
                    p=None
        else:
            p = page

        if p is None:
            edit_url = ""
            delete_url = ""
        else:
            edit_url = reverse(self.page_edit_url,kwargs={'page':p.slug})
            delete_url = reverse(self.page_delete_url,kwargs={'page':p.slug})

        left_sidebar_func = None
        if isinstance(settings.LEFT_SIDEBAR_FUNCTION,str):
            _func = import_string(settings.LEFT_SIDEBAR_FUNCTION)
            if callable(_func):
                left_sidebar_func = _func
        elif callable(settings.LEFT_SIDEBAR_FUNCTION):
            left_sidebar_func = settings.LEFT_SIDEBAR_FUNCTION
        
        if callable(left_sidebar_func):
            left_sidebar_spec = left_sidebar_func(request)
        else:
            left_sidebar_spec = None
        

        context = {
            'base_template': self.base_template,
            'css': self.css,
            'user_can_create_pages': self.get_user_can_create_pages(request.user),
            'user_can_delete_page': self.get_user_can_delete_page(request.user,page),
            'user_can_edit_page': self.get_user_can_edit_page(request.user,page),
            'user_is_wiki_admin': self.get_user_is_wiki_admin(request.user),
            'header_title': self.header_title,
            'page_view_url': self.page_view_url,
            'login_url': self.login_url if not login_url else login_url,
            'logout_url': self.logout_url,
            'signup_url': self.signup_url,
            'home_url': self.home_url,
            'edit_url': edit_url,
            'delete_url': delete_url,
            'create_url': reverse(self.page_new_url),
            'overview_url': self.overview_url,
            'page_url': self.page_view_url,
            'index_url': self.index_url,
            'left_sidebar_spec': left_sidebar_spec,
        }
        context.update(kwargs)
        context.update(self.context_callback(request))

        return context
    
    def build_login_url(self,request):
        return self.login_url + "?n=" + urlsafe_base64_encode(request.build_absolute_uri().encode('utf-8'))

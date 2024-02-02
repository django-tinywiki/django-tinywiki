from django.shortcuts import render,redirect,get_object_or_404
from django.urls import reverse
from django.views import View
from django.utils.translation import gettext
from django.contrib.auth import get_user_model
from django.core.files import File

from PIL import Image

import re

_ = gettext

from .. import settings

from ..models import (
    WikiPage,
    WikiPageBackup,
    WikiLanguage,
    WikiImage
)

from ..forms.wiki import (
    PageForm,
    ImageUploadForm,
)

import os

from ..functions import (
    user_can_create_pages,
    get_language_code,
    render_markdown)

from .view import ViewBase
# Create your views here.

class WikiPageView(ViewBase):
    page_template = settings.TINYWIKI_PAGE_VIEW_TEMPLATE
    image_upload_url = settings.TINYWIKI_IMAGE_UPLOAD_URL

    def get_context(self,request,page=None,**kwargs):
        context = super().get_context(request,page=page,**kwargs)
        if page:
            page_context = {
                'slug':page.slug,
                'title': page.title,
                'language': page.language.code,
                'edit_page': self.get_user_can_edit_page(request.user,page),
            }
            context.update({
                "header_subtitle": page.title,
                "title":page.title,
                "content": render_markdown(page.content,page_context),
                'image_upload_url': reverse(self.image_upload_url,kwargs={'page':page.slug}),
            })

        return context

    def get(self,request,page):

        page_context = {}
        try:
            p = WikiPage.objects.get(slug=page)
            pattern = re.compile("\!\[\[([0-9]+?)\]\]")
            page_images = p.images.all()
            re_linked_images = [int(i) for i in re.findall(pattern,p.content)]            

            orphaned_images = []
            image_ids = []


            for i in page_images:
                image_ids.append(i.id)
                if i.id not in re_linked_images:
                    orphaned_images.append(i)   
            
            context = self.get_context(request=request,page=p,
                                       images=page_images,
                                       orphaned_images=orphaned_images,
                                       login_url=self.build_login_url(request))

        except WikiPage.DoesNotExist:
            if self.get_user_can_create_pages(request.user):
                return redirect(reverse(settings.TINYWIKI_PAGE_CREATE_URL,args=[page]))

            context = self.get_context(request)

            content_file = os.path.join(os.path.dirname(__file__),"en.404.md")
            title = _("404 - Page not found!")
            check_file = os.path.join(os.path.dirname(__file__),'.'.join((get_language_code,"404","md")))
            if os.path.isfile(check_file):
                content_file = check_file

            with open(content_file,"r") as ifile:
                page_content = ifile.read()

            context.update({
                'header_subtitle': title,
                'title': title,
                'content': render_markdown(page_content,page_context)
            })

        return render(request,self.page_template,context)

class WikiIndexView(WikiPageView):
    index_page=settings.TINYWIKI_INDEX

    def get(self,request):
        return WikiPageView.get(self,request,page=self.index_page)

class WikiCreateView(ViewBase):
    template = settings.TINYWIKI_PAGE_EDIT_TEMPLATE
    
    def get(self,request,page=None):
        context=self.get_context(request=request)
        if page:
            try:
                p = WikiPage.objects.get(slug=page)
                return redirect(reverse(settings.TINYWIKI_PAGE_EDIT_URL,kwargs={'page':page}))
            except WikiPage.DoesNotExist:
                pass
        #user_language = request.user.wiki_language
        form_defaults={
            'user':request.user,
        }
        if page is not None:
            form_defaults['slug'] = page
        context['form'] = PageForm(form_defaults)
        return render(request,self.template,context)

    def post(self,request,page=None):
        context = self.get_context(request=request,page=page)

        form = PageForm(request.POST)
        context['form'] = form

        if form.is_valid():
            UserModel = get_user_model()
            try:
                user = UserModel.objects.get(id=form.cleaned_data['user'])
            except UserModel.DoesNotExist:
                user = request.user

            try:
                language = WikiLanguage.objects.get(code=form.cleaned_data['language'])
            except WikiLanguage.DoesNotExist:
                language = WikiLanguage.objects.all().order_by('id')[0]
                
            create_page_kwargs = {
                'slug': form.cleaned_data['slug'],
                'user': user,
                'title': form.cleaned_data['title'],
                'language': language,
                'content': form.cleaned_data['content'],
                'created_by': request.user,
                'edited_by': request.user,
                'userlock': form.cleaned_data['userlock'],
                'editlock': form.cleaned_data['editlock'],
                'edited_reason': "Page created",
            }

            try:
                p = WikiPage.objects.create(**create_page_kwargs)
                return redirect(reverse(settings.TINYWIKI_PAGE_VIEW_URL,kwargs={'page':p.slug}))
            except Exception as error:
                context['error'] = str(error)
                
        return render(request,self.template,context)

class WikiEditView(ViewBase):
    template = settings.TINYWIKI_PAGE_EDIT_TEMPLATE

    def get(self,request,page):
        
        try:
            p = WikiPage.objects.get(slug=page)
        except WikiPage.DoesNotExist:
            return redirect(reverse(settings.TINYWIKI_PAGE_CREATE_URL,kwargs={'page':page}))
        
        if p.user:
            page_user_id = p.user.id
        else:
            page_user_id = request.user.id

        form_data={
            'slug':page,
            'user':page_user_id,
            'language':p.language.code,
            'title': p.title,
            'content': p.content,
            'userlock': p.userlock,
            'editlock': p.editlock
        }
        form = PageForm(form_data)

        context = self.get_context(request=request,page=p,form=form,slug=p.slug)
        
        return render(request,self.template,context)
    
    def post(self,request,page):
        
        try:
            p = WikiPage.objects.get(id=page)
        except WikiPage.DoesNotExist:
            return redirect(reverse(settings.TINYWIKI_PAGE_CREATE_URL,kwargs={'page':page}))
        
        form = PageForm(request.POST)
        if form.is_valid():
            UserModel = get_user_model()
            
            backup_kwargs = {
                'wiki_page': p,
                'slug': p.slug,
                'title': p.title,
                'language': p.language,
                'content': p.content,
                'user': p.user,
                'created_on': p.created_on,
                'created_by': p.created_by,
                'edited_on': p.edited_on,
                'edited_by': p.edited_by,
                'edited_reason': p.edited_reason
            }
            pbackup = WikiPageBackup.objects.create(**backup_kwargs)

            if p.slug != form.cleaned_data['slug']:
                p.slug = form.cleaned_data['slug']

            p.title = form.cleaned_data['title']
            try:
                p.user = UserModel.objects.get(id=form.cleaned_data['user'])
            except UserModel.DoesNotExist:
                pass

            try:
                p.language = WikiLanguage.objects.get(code=form.cleaned_data['language'])
            except WikiLanguage.DoesNotExist:
                pass

            p.content = form.cleaned_data['content']
            p.editlock = form.cleaned_data['editlock']
            p.userlock = form.cleaned_data['userlock']
            p.edited_by = request.user
            p.edited_reason = form.cleaned_data['edited_reason']
            p.save()

            return redirect(reverse(settings.TINYWIKI_PAGE_VIEW_URL,kwargs={'page':p.slug}))

        context = self.get_context(request=request,page=p,form=form,slug=p.slug)

        return render(request,self.base_template,context)
    
class WikiImageUploadView(ViewBase):
    template = settings.TINYWIKI_IMAGE_UPLOAD_TEMPLATE
    image_upload_directory = settings.TINYWIKI_IMAGE_UPLOAD_DIRECTORY

    def get(self,request,page):
        p = get_object_or_404(WikiPage,slug=page)

        form = ImageUploadForm()

        context = self.get_context(request=request,page=p,form=form)
        return render(request,self.template,context)

    def post(self,request,page):
        p = get_object_or_404(WikiPage,slug=page)

        form = ImageUploadForm(request.POST,request.FILES)
        if form.is_valid():

            img_create_kwargs = {
                    'wiki_page': p,
                    'alt': form.cleaned_data['alt_text'],
                    'description': form.cleaned_data['description'],
                    'image': form.cleaned_data['image'],
                    'uploaded_by': request.user,
            }
            image = p.images.create(**img_create_kwargs)
            image.save()

            orig_img = Image.open(image.image.path,'r')
            wrkdir = os.path.join(self.image_upload_directory,str(p.id))

            if not os.path.exists(wrkdir):
                os.makedirs(wrkdir)
            orig_name = image.image.path
            fn,fext=os.path.splitext(os.path.basename(orig_name))


            wiki_name = os.path.join(wrkdir,fn + '.wiki' + fext)
            preview_name = os.path.join(wrkdir,fn + '.preview' + fext)
            sidebar_name = os.path.join(wrkdir,fn + '.sidebar' + fext)

            
            width,height = orig_img.size

            if width > settings.TINYWIKI_IMAGE_WIKI_WIDTH:
                new_size = (settings.TINYWIKI_IMAGE_WIKI_WIDTH, int((height * (settings.TINYWIKI_IMAGE_WIKI_WIDTH / width)) + 0.5))
                wiki_img = orig_img.resize(new_size)
                wiki_img.save(wiki_name)
                wiki_img.close()
            else:
                wiki_name = orig_name
            
            if width > settings.TINYWIKI_IMAGE_SIDEBAR_WIDTH:
                new_size = (settings.TINYWIKI_IMAGE_SIDEBAR_WIDTH, int((height * (settings.TINYWIKI_IMAGE_PREVIEW_WIDTH / width))+ 0.5))
                sb_img = orig_img.resize(new_size)
                sb_img.save(sidebar_name)
                sb_img.close()
            else:
                sidebar_name = orig_name

            if width > settings.TINYWIKI_IMAGE_PREVIEW_WIDTH:
                new_size = (settings.TINYWIKI_IMAGE_PREVIEW_WIDTH, int((height * (settings.TINYWIKI_IMAGE_PREVIEW_WIDTH / width)) + 0.5))
                prev_img = orig_img.resize(new_size)
                prev_img.save(preview_name)
                prev_img.close()
            else:
                preview_name = orig_name

            orig_img.close()

            with (open(wiki_name,'rb') as wf, open(sidebar_name,'rb') as sf, open(preview_name,'rb') as pf):
                wiki_file = File(wf,name=os.path.basename(wiki_name))
                sidebar_file = File(sf,name=os.path.basename(sidebar_name))
                preview_file = File(pf,name=os.path.basename(preview_name))

                image.image_wiki = wiki_file
                image.image_sidebar = sidebar_file
                image.image_preview = preview_file
                image.save()
                
            if preview_name != orig_name:
                os.unlink(preview_name)
            if sidebar_name != orig_name:
                os.unlink(sidebar_name)
            if wiki_name != orig_name:
                os.unlink(wiki_name)

            return redirect(reverse(self.page_view_url,kwargs={'page':page}))
        
        context = self.get_context(request=request,page=p,form=form)

        return render(request,self.template,context)

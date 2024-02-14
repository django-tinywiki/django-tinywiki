from django.utils.translation import gettext as _
from django.core.files import File
from .. import settings
from ..models import WikiLanguage,WikiPage,WikiPageBackup,WikiImage
import os
import PIL
import re
from shutil import copyfile
import hashlib
import markdown
from django.template import Context,Template

def install_builtin_image(user,wikipage,file:str,builtin_id:int,alt="Image",description=None):
    try: 
        wi = WikiImage.objects.get(builtin_id=builtin_id)
    except WikiImage.DoesNotExist:
        if not os.path.isfile(file):
            raise FileNotFoundError(_("Image file \"{file}\" for BuiltinID \"{builtin_id}\" not found!").format(file=file,builtin_id=builtin_id))
        
        wrkdir = settings.TINYWIKI_IMAGE_UPLOAD_DIRECTORY
        if not os.path.isdir(wrkdir):
            os.makedirs(wrkdir)
            print("[django-tinywiki] directory \"{dir}\" created".format(dir=wrkdir))

        wi = None
        try:
            name,ext = os.path.splitext(file)
        except:
            raise ValueError(_("Image file \"{file}\" has no file extension! SKIPPING!").format(file=filename))
            
        
        if ext.lower() == ".svg":
            convert_image = False
        else:
            convert_image = True

        new_fname = "builtin.{builtin_id}{extension}".format(builtin_id=builtin_id,extension=ext)
        orig_img_path = os.path.join(wrkdir,"original." + new_fname)
        wiki_img_path = os.path.join(wrkdir,"wiki." + new_fname)
        preview_img_path = os.path.join(wrkdir,"preview." + new_fname)
        sidebar_img_path = os.path.join(wrkdir,"sidebar." + new_fname)

        copyfile(file,orig_img_path)

        orig_img = PIL.Image.open(orig_img_path)
        img_width,img_height = orig_img.size

        if (convert_image and img_width > settings.TINYWIKI_IMAGE_WIKI_WIDTH):
            wiki_img = orig_img.resize((settings.TINYWIKI_IMAGE_WIKI_WIDTH,
                                        int((img_height * (settings.TINYWIKI_IMAGE_WIKI_WIDTH / img_width)) + 0.5)))
            wiki_img.save(wiki_img_path)
            wiki_img.close()
        else:
            copyfile(file,wiki_img_path)

        if (convert_image and img_width > settings.TINYWIKI_IMAGE_PREVIEW_WIDTH):
            prev_img = orig_img.resize((settings.TINYWIKI_IMAGE_PREVIEW_WIDTH,
                                        int((img_height * (settings.TINYWIKI_IMAGE_PREVIEW_WIDTH / img_width)) + 0.5)))
            prev_img.save(preview_img_path)
            prev_img.close()
        else:
            copyfile(file,preview_img_path)

        if (convert_image and img_width > settings.TINYWIKI_IMAGE_PREVIEW_WIDTH):
            sb_img = orig_img.resize((settings.TINYWIKI_IMAGE_SIDEBAR_WIDTH,
                                      int((img_height * (settings.TINYWIKI_IMAGE_SIDEBAR_WIDTH / img_width)) + 0.5)))
            sb_img.save(sidebar_img_path)
            sb_img.close()
        else:
            copyfile(file,sidebar_img_path)

        orig_img.close()

        with open(orig_img_path) as orig_img_fp, open(wiki_img_path) as wiki_img_fp, open(preview_img_path) as preview_img_fp, open(sidebar_img_path) as sidebar_img_fp:
            orig_img_file = File(orig_img_fp,name=os.path.basename(orig_img_path))
            wiki_img_file = File(wiki_img_fp,name=os.path.basename(wiki_img_path))
            preview_img_file = File(preview_img_fp,name=os.path.basename(preview_img_path))
            sidebar_img_file = File(sidebar_img_fp,name=os.path.basename(sidebar_img_path))

            wi = WikiPage.objects.add(wiki_page=wikipage,
                                      builtin_id=builtin_id,
                                      alt=alt,
                                      description=description,
                                      image=orig_img_file,
                                      image_wiki=wiki_img_file,
                                      image_preview=preview_img_file,
                                      image_sidebar=sidebar_img_file,
                                      uploaded_by=user)
            wi.save()
            print("[django-tinywiki] Image {img} added to wiki-page {slug}".format(img=os.path.basename(file),slug=wikipage.slug))
        
        for i in [orig_img_path,wiki_img_path,preview_img_path,sidebar_img_path]:
            if os.path.exists(i):
                os.unlink(i)

    return wi

def install_builtin_wiki_page(user,file,slug,title,language,images=None):
    (PAGE_UNCHANGED,PAGE_UPDATED,PAGE_CREATED) = range(3)
    page_mode = PAGE_UNCHANGED

    if not os.path.isfile(file):
        raise FileNotFoundError(_("Makrdown file \"{file}\" not found!").format(file=file))

    try:
        wikipage = WikiPage.objects.get(slug=slug)
        page_changed = False

        backup_kwargs = {
            'wiki_page': wikipage,
            'slug': wikipage.slug,
            'title': wikipage.title,
            'language': wikipage.language,
            'user': wikipage.user,
            'content': wikipage.content,
            'created_on': wikipage.created_on,
            'created_by': wikipage.created_by,
            'edited_on': wikipage.edited_on,
            'edited_by': wikipage.edited_by,
            'edited_reason': wikipage.edited_reason,
        }

        with open(file,"rb",) as contentfile_bin:
            contentfile_md5 = hashlib.md5(contentfile_bin.read()).hexdigest()
        
        if wikipage.title != title or wikipage.contentfile_md5 is None or wikipage.contentfile_md5 != contentfile_md5:
            page_changed = True

        if page_changed:
            wikipagebackup = WikiPageBackup.objects.create(**backup_kwargs)
            wikipagebackup.save()


            wikipage.title = title
            wikipage.edited_by = user
            with open(file,"r",encoding="utf-8") as contentfile:
                wikipage.content = contentfile.read()
            wikipage.contentfile_md5 = contentfile_md5
            wikipage.edited_reason = "Update"
            wikipage.save()
            page_mode = PAGE_UPDATED
    except WikiPage.DoesNotExist:
        with open(file,"r",encoding="utf-8") as contentfile:
            content = contentfile.read()

        with open(file,"rb") as contentfile_bin:
            contentfile_md5 = hashlib.md5(contentfile_bin.read()).hexdigest()

        if isinstance(language,str):
            try:
                wikilang = WikiLanguage.objects.get(code=language)
            except WikiLanguage.DoesNotExist:
                wikilang = WikiLanguage.objects.get('en')
        else:
            wikilang = language

        wikipage = WikiPage.objects.create(
            slug=slug,
            title=title,
            langauge=wikilang,
            content=content,
            contentfile_md5=contentfile_md5,
            user=user,
            edited_by=user,
            created_by=user,
            edited_reason="create page"
        )
        page_mode = PAGE_CREATED

    if page_mode == PAGE_UPDATED:
        print("[django-tinywiki] Page {slug} updated".format(slug=wikipage.slug))
    elif page_mode == PAGE_CREATED:
        print("[django-tinywiki] Page {slug} created".format(slug=wikipage.slug))

    if images:
        for img_spec in images:
            wikiimage = install_builtin_image(user,wikipage,**img_spec)
            re_pattern = "\!\[\[\-\-[\-]?{}\-\-\]\]".format(wikiimage.builtin_id)
            recp = re.compile(re_pattern)
            wikipage.content = re.sub(recp,"![[{}]]".format(wikiimage.id),wikipage.content)
            wikipage.save()
    return wikipage

def get_language_code(self):
    x = _("language-code")
    if x == "language-code":
        return "en"
    return x

def render_markdown(string,context=None):
    if context is None:
        context={}

    c = Context(context)
    t = Template(string)
    if context and 'slug' in context:
        slug = context['slug']
    else:
        slug = None

    if context and 'edit_page' in context:
        edit_page = context['edit_page']
    else:
        edit_page = False
        

    s = t.render(c)
    return markdown.markdown(s,extensions=settings.TINYWIKI_MARKDOWN_EXTENSIONS,
                             extension_configs = {
                                "django_tinywiki.markdown_extensions:TinywikiLinkedImagesExtension": {
                                   'wiki_page': slug,
                                   'edit_page': edit_page,
                                }
                            })
import cfnlint
from pathlib import Path
from taskcat.client_factory import ClientFactory
from taskcat.common_utils import s3_url_maker
from typing import List, Set
import logging
import random
import string

LOG = logging.getLogger(__name__)


class Template:

    def __init__(self, template_path: str, project_root: str = '', url: str = '',
                 client_factory_instance: ClientFactory = ClientFactory()):
        self.template_path: Path = Path(template_path).absolute()
        self.template = cfnlint.decode.cfn_yaml.load(self.template_path)
        with open(template_path, 'r') as fh:
            self.raw_template = fh.read()
        project_root = project_root if project_root else self.template_path.parent.parent
        self.project_root = Path(project_root).absolute()
        self.client_factory_instance = client_factory_instance
        self.url = url
        self.children: List[Template] = []
        self._find_children()

    def __str__(self):
        return str(self.template)

    def __repr__(self):
        return "<Template {} at {}>".format(self.template_path, hex(id(self)))

    def _upload(self, bucket_name: str, prefix: str = '') -> str:
        s3_client = self.client_factory_instance.get('s3')
        s3_client.upload_file(str(self.template_path), bucket_name, prefix + self.template_path.name)
        return s3_url_maker(bucket_name, f'{prefix}{self.template_path.name}', self.client_factory_instance.get('s3'))

    def _delete_s3_object(self, url):
        if url:
            bucket_name = url.split('//')[1].split('.')[0]
            path = '/'.join(url.split('//')[1].split('/')[1:])
            s3_client = self.client_factory_instance.get('s3')
            s3_client.delete_objects(Bucket=bucket_name, Delete={'Objects': [{'Key': path}], 'Quiet': True})

    def write(self):
        """writes raw_template back to file, and reloads decoded template, useful if the template has been modified"""
        with open(str(self.template_path), 'w') as fh:
            fh.write(self.raw_template)
        self.template = cfnlint.decode.cfn_yaml.load(self.template_path)
        self._find_children()

    def validate(self, region, bucket_name: str = '', prefix: str = ''):
        cfn_client = self.client_factory_instance.get('cloudformation', region)
        if not self.url and not bucket_name:
            raise ValueError("validate requires either the url instance variable, or bucket_name+prefix to be provided")
        tmpurl = ''
        if not self.url:
            rand = ''.join(random.choice(string.ascii_lowercase) for i in range(8)) + '/'
            tmpurl = self._upload(bucket_name, prefix+rand)
        url = tmpurl if tmpurl else self.url
        try:
            cfn_client.validate_template(TemplateURL=url)
        except cfn_client.exceptions.ClientError as e:
            self._delete_s3_object(tmpurl)
            if e.response["Error"]["Code"] == "ValidationError":
                return "{} - {} - {}".format(self.template_path, region, e.response["Error"]["Message"])
            raise
        self._delete_s3_object(tmpurl)
        return None

    def _template_url_to_path(self, template_url):
        if isinstance(template_url, dict):
            if 'Fn::Sub' in template_url.keys():
                if isinstance(template_url['Fn::Sub'], str):
                    template_path = template_url['Fn::Sub'].split('}')[-1]
                else:
                    template_path = template_url['Fn::Sub'][0].split('}')[-1]
            elif 'Fn::Join' in list(template_url.keys())[0]:
                template_path = template_url['Fn::Join'][1][-1]
        elif isinstance(template_url, str):
            template_path = '/'.join(template_url.split('/')[-2:])
        template_path = self.project_root / template_path
        if template_path.exists():
            return template_path
        LOG.error(f"Failed to discover path for {template_url}, path {template_path} does not exist")
        return ''

    def _get_relative_url(self, path: str) -> str:
        url = ''
        if self.url:
            suffix = str(self.template_path).replace(str(self.project_root), '')
            suffix_length = len(suffix.lstrip('/').split("/"))
            url_prefix = '/'.join(self.url.split('/')[0:-suffix_length])
            suffix = str(path).replace(str(self.project_root), '')
            url = url_prefix + suffix
        return url

    def url_prefix(self) -> str:
        url_prefix = ''
        if self.url:
            suffix = str(self.template_path).replace(str(self.project_root), '')
            suffix_length = len(suffix.lstrip('/').split("/"))
            url_prefix = '/'.join(self.url.split('/')[0:-suffix_length])
        return url_prefix

    def _find_children(self) -> None:
        children = set()
        for resource in self.template['Resources'].keys():
            resource = self.template['Resources'][resource]
            if resource['Type'] == "AWS::CloudFormation::Stack":
                child_name = self._template_url_to_path(resource['Properties']['TemplateURL'])
                if child_name:
                    children.add(child_name)
        for child in children:
            child_template_instance = None
            for d in self.descendents():
                if str(d.template_path) == str(child):
                    child_template_instance = d
            if not child_template_instance:
                child_template_instance = Template(child, self.project_root, self._get_relative_url(child),
                                                   self.client_factory_instance)
            self.children.append(child_template_instance)

    def descendents(self) -> Set['Template']:

        def recurse(template, descendants):
            descendants = descendants.union(set(template.children))
            for child in template.children:
                descendants = descendants.union(recurse(child, descendants))
            return descendants

        return recurse(self, set())
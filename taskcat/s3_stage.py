
class S3APIResponse:
    def __init__(self, x):
        self._http_code = x['ResponseMetadata']['HTTPStatusCode']

    @property
    def ok(self):
        if self._http_code == 200:
            return True
        return False

class S3BucketCreatorException(Exception):
    pass

class S3BucketCreator:
    def __init__(self, config: Config):
        self.name = ""
        self.public = False
        self.tags = []
        self.region = 'us-east-1'
        self.sigv4 = True
        self._config = config
        self._c = None

    @property
    def acl(self):
        return self._acl

    @property
    def policy(self):
        return self._policy

    def _create_in_region(self, region):
        if region == 'us-east-1':
            response = self._c.create_bucket(
                ACL=self.acl,
                Bucket=self.name
            )
        else:
            response = self._c.create_bucket(
                ACL=self.acl,
                Bucket=self.name,
                CreateBucketConfiguration={
                    'LocationConstraint': region
                }
            )

        return S3APIResponse(response)

    def _return_sigv4_policy(self, bucket):
        policy = F"""{
            "Version": "2012-10-17",
            "Statement": [
                {
                    "Sid": "Test",
                    "Effect": "Deny",
                    "Principal": "*",
                    "Action": "s3:*",
                    "Resource": "arn:aws:s3:::{bucket}/*",
                    "Condition": {
                         "StringEquals": {
                               "s3:signatureversion": "AWS"
                         }
                    }
                }
            ]
        }"""

    def create(self):
        # Verify bucket name length
        if len(self.name) > self.config.s3_bucket.max_name_len:
            raise S3BucketCreatorException(f"The bucket you provided [{config.s3_bucket.name}] is greater than {config.s3_bucket.max_name_len} characters.")

        s3_client = config.client_factory.get('s3', region=config.default_region, s3v4=self.sigv4)

        if not config.s3_bucket.name:

            # Verify bucket exists.
            try:
                _ = s3_client.list_objects(Bucket=config.s3_bucket.name)
            except s3_client.exceptions.NoSuchBucket:
                raise TaskCatException(f"The bucket you provided ({self.name}) does not exist. Exiting.")
            except Exception:
                raise

        else:
            auto_bucket_name = f"taskcat-{self.stack_prefix}-{self.name}-{self.uuid}".lower()
            log.info(f"Creating bucket {auto_bucket_name} in {self.region}")
            config.s3_bucket.auto = True

            _create_resp = self._create_in_region(self.region):
            if _create_resp.ok:
                log.info(f"Staging Bucket: [{auto_bucket_name}]")

            if self.tags:
                s3_client.put_bucket_tagging(
                    Bucket=auto_bucket,
                    Tagging={"TagSet": self.tags}
                )

            if self.sigv4:
                log.info(f"Enforcing sigv4 requests for bucket ${auto_bucket}")
                policy = self._return_sigv4_policy(self.name)
                s3_client.put_bucket_policy(Bucket=self.name, Policy=policy)


def new_stage_in_s3(self, config: Config):
    """
    Upload templates and other artifacts to s3.

    This function creates the s3 bucket with name provided in the config yml file. If
    no bucket name provided, it creates the s3 bucket using project name provided in
    config yml file. And uploads the templates and other artifacts to the s3 bucket.

    :param config: Taskcat config object.

    """
    S3Bucket = S3BucketCreator(config)

    if config.s3_bucket.name:
      S3Bucket.name = config.s3_bucket.name

    if config.s3_bucket.public:
      S3Bucket.public = True

    if config.s3_bucket.tags:
      S3Bucket.tags = config.s3_bucket.tags

    if config.default_region != 'us-east-1':
      S3Bucket.region = config.default_region

    if config.sigv4:
      S3Bucket.sigv4 = True

    try:
      S3Bucket.create()
    except Exception as e:
      raise TaskCatException(e)

    S3Sync(s3_client,
           self.get_s3bucket(),
           self.get_project_name(),
           self.get_project_path(),
           bucket_or_object_acl)

    # self.s3_url_prefix = "https://" + self.get_s3_hostname() + "/" + self.get_project_name()

    if self.upload_only:
        exit0("Upload completed successfully")

def stage_in_s3(self, config: Config):
    """
    Upload templates and other artifacts to s3.

    This function creates the s3 bucket with name provided in the config yml file. If
    no bucket name provided, it creates the s3 bucket using project name provided in
    config yml file. And uploads the templates and other artifacts to the s3 bucket.

    :param config: Taskcat config object.

    """

    def _verify_bucket_len(name, length):
        if len(name) > length:
            raise TaskCatException(f"The bucket you provided [{config.s3_bucket.name}] is greater than {config.s3_bucket.max_name_len} characters.")

    if config.s3_bucket.public:
        bucket_object_acl = "public-read"
    else:
        bucket_object_acl = "bucket-owner-read"

    #TODO CLIENTFACTORY
    #TODO config.s3_bucket.name
    #TODO jobid.
    s3_client = config.client_factory.get('s3', region=config.default_region, s3v4=True)

    if config.s3_bucket.name:
        # Verify name length constraints.
        _verify_bucket_len(config.s3_bucket.name, config.s3_bucket.max_name_len)

        # Verify bucket exists.
        try:
            _ = s3_client.list_objects(Bucket=config.s3_bucket.name)
        except s3_client.exceptions.NoSuchBucket:
            raise TaskCatException(f"The bucket you provided [{config.s3_bucket.name}] does not exist. Exiting.")
        except Exception:
            raise

        log.info(f"Staging Bucket => {config.s3_bucket.name}")

    else:

        auto_bucket = f"taskcat-{config.stack_prefix}-{config.name}-{self._jobid[:8]".lower()

        _verify_bucket_len(auto_bucket, config.s3_bucket.max_name_len)

        log.info(f"Creating bucket {config.s3_bucket} in {config.default_region}")
        if config.default_region == 'us-east-1':
            response = s3_client.create_bucket(
                    ACL=bucket_object_acl,
                    Bucket=auto_bucket)
        else:
            response = s3_client.create_bucket(
                    ACL=bucket_object_acl,
                    CreateBucketConfiguration={
                        'LocationConstraint': config.default_region
                        }
                    )
        config.s3_bucket.auto = True

        else:
            raise TaskCatException("Default_region = " + self.get_default_region())

        if response['ResponseMetadata']['HTTPStatusCode'] is 200:
            log.info("Staging Bucket => [%s]" % auto_bucket)
            self.set_s3bucket(auto_bucket)
        else:
            log.info('Creating bucket {0} in {1}'.format(auto_bucket, self.get_default_region()))
            response = s3_client.create_bucket(ACL=bucket_or_object_acl,
                                               Bucket=auto_bucket,
                                               CreateBucketConfiguration={
                                                   'LocationConstraint': self.get_default_region()})

            if response['ResponseMetadata']['HTTPStatusCode'] is 200:
                log.info("Staging Bucket => [%s]" % auto_bucket)
                self.set_s3bucket(auto_bucket)
        if self.tags:
            s3_client.put_bucket_tagging(
                Bucket=auto_bucket,
                Tagging={"TagSet": self.tags}
            )
        if not self.enable_sig_v2:
            print(PrintMsg.INFO + "Enforcing sigv4 requests for bucket %s" % auto_bucket)
            policy = """{
"Version": "2012-10-17",
"Statement": [
     {
           "Sid": "Test",
           "Effect": "Deny",
           "Principal": "*",
           "Action": "s3:*",
           "Resource": "arn:aws:s3:::%s/*",
           "Condition": {
                 "StringEquals": {
                       "s3:signatureversion": "AWS"
                 }
           }
     }
]
}
""" % auto_bucket
            s3_client.put_bucket_policy(Bucket=auto_bucket, Policy=policy)

    for exclude in self.get_exclude():
        if os.path.isdir(exclude):
            S3Sync.exclude_path_prefixes.append(exclude)
        else:
            S3Sync.exclude_files.append(exclude)

    S3Sync(s3_client, self.get_s3bucket(), self.get_project_name(), self.get_project_path(), bucket_or_object_acl)
    self.s3_url_prefix = "https://" + self.get_s3_hostname() + "/" + self.get_project_name()
    if self.upload_only:
    exit0("Upload completed successfully")
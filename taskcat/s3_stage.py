    def stage_in_s3(self, config: Config):
        """
        Upload templates and other artifacts to s3.

        This function creates the s3 bucket with name provided in the config yml file. If
        no bucket name provided, it creates the s3 bucket using project name provided in
        config yml file. And uploads the templates and other artifacts to the s3 bucket.

        :param taskcat_cfg: Taskcat configuration provided in yml file

        """
        if self.public_s3_bucket:
            bucket_or_object_acl = 'public-read'
        else:
            bucket_or_object_acl = 'bucket-owner-read'
        s3_client = self._boto_client.get('s3', region=self.get_default_region(), s3v4=True)

        if 's3bucket' in taskcat_cfg['global'].keys():
            self.set_s3bucket(taskcat_cfg['global']['s3bucket'])
            self.set_s3bucket_type('defined')
            log.info("Staging Bucket => " + self.get_s3bucket())
            if len(self.get_s3bucket()) > self._max_bucket_name_length:
                raise TaskCatException("The bucket name you provided is greater than {} characters.".format(self._max_bucket_name_length))
            try:
                _ = s3_client.list_objects(Bucket=self.get_s3bucket())
            except s3_client.exceptions.NoSuchBucket:
                raise TaskCatException("The bucket you provided [{}] does not exist. Exiting.".format(self.get_s3bucket()))
            except Exception:
                raise
        else:
            auto_bucket = 'taskcat-' + self.stack_prefix + '-' + self.get_project_name() + "-" + self._jobid[:8]
            auto_bucket = auto_bucket.lower()
            if len(auto_bucket) > self._max_bucket_name_length:
                auto_bucket = auto_bucket[:self._max_bucket_name_length]
            if self.get_default_region():
                log.info('Creating bucket {0} in {1}'.format(auto_bucket, self.get_default_region()))
                if self.get_default_region() == 'us-east-1':
                    response = s3_client.create_bucket(ACL=bucket_or_object_acl,
                                                       Bucket=auto_bucket)
                else:
                    response = s3_client.create_bucket(ACL=bucket_or_object_acl,
                                                       Bucket=auto_bucket,
                                                       CreateBucketConfiguration={
                                                           'LocationConstraint': self.get_default_region()
                                                       })

                self.set_s3bucket_type('auto')
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
data "external" "build" {
  program = ["python", "build.py"]
  query = {
    install_command  = var.install-command
    build_command    = var.build-command
    webapp_dir       = var.webapp-dir
    build_destiation = var.build-destination
    # you can change the following, if you do, please update the build.py
    production = "true"
  }
  working_dir = path.module
}

# upload frontend files to aws
resource "null_resource" "app_s3_upload" {
  triggers = {
    compiled_code_hash = data.external.build.result.hash
    build_file_hash    = filesha1("./build.py")
  }

  # we upload to the frontend folder in s3, then we can re-use bucket's other directories for other things
  provisioner "local-exec" {
    command = "aws s3 sync \"${var.build-destination}\" \"s3://${aws_s3_bucket.app_bucket.id}/frontend\" --delete"
  }

  depends_on = [
    aws_s3_bucket.app_bucket
  ]
}

# invalidate caches
resource "null_resource" "cloudfront_invalidate" {
  triggers = {
    compiled_code_hash = data.external.build.result.hash
  }

  provisioner "local-exec" {
    command = "aws cloudfront create-invalidation --distribution-id ${aws_cloudfront_distribution.app_distribution.id} --paths '/*'"
  }

  depends_on = [
    null_resource.app_s3_upload,
  ]
}

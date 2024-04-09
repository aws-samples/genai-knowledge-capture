import os
import os.path as path
from aws_cdk import (
    Duration,
    Stack,
    Aws,
    RemovalPolicy,
    CfnOutput,
    aws_kms as kms,
    aws_iam as iam,
    aws_s3 as s3,
    aws_logs as logs,
    aws_lambda as lambda_,
    aws_s3_deployment as s3deploy,
    aws_stepfunctions as sfn,
    aws_sns as sns,
)
from constructs import Construct
from aws_cdk.aws_ecr_assets import Platform
from cdk_nag import NagSuppressions


PARENT_DIR: str = path.join(os.path.dirname(__file__), "..")
AUDIO_SAMPLES_PATH: str = path.join(PARENT_DIR, "assets", "audio_samples")
LAMBDA_PATH: str = path.join(PARENT_DIR, "code", "lambdas")
POWERTOOLS_ARN: str = (
    f"arn:aws:lambda:{Aws.REGION}:017000801446:layer:AWSLambdaPowertoolsPythonV2:67"
)
APP_LOG_LEVEL = "INFO"


class CodeStack(Stack):
    """
    Define all AWS resources for the app
    """

    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        kms_key: kms.Key = self.create_kms_key()
        audio_bucket: s3.Bucket = self.create_data_source_bucket(kms_key)
        sns_topic: sns.Topic = self.create_sns_topic(kms_key)
        self.upload_assets_to_bucket(audio_bucket, kms_key)
        (
            lambda_function_preprocess,
            lambda_function_transcribe,
            lambda_function_validate,
            lambda_function_summarize,
            lambda_function_generate,
        ) = self.create_lambda_functions(audio_bucket, kms_key)
        self.create_step_functions_state_machine(
            kms_key,
            sns_topic,
            lambda_function_preprocess,
            lambda_function_transcribe,
            lambda_function_validate,
            lambda_function_summarize,
            lambda_function_generate,
        )

    def create_sns_topic(self, kms_key: kms.Key) -> sns.Topic:
        """
        Create a SNS topic to publish notification for any error/exception occured
        """

        sns_topic = sns.Topic(
            self,
            id="SNSTopic",
            display_name=f"{Aws.STACK_NAME}-sns",
            master_key=kms_key,
            enforce_ssl=True,
        )

        sns_policy_statement = iam.PolicyStatement(
            effect=iam.Effect.ALLOW,
            actions=["sns:Subscribe", "sns:Publish"],
            principals=[iam.AnyPrincipal()],
            resources=[sns_topic.topic_arn],
            conditions={
                "StringEquals": {
                    "AWS:SourceOwner": iam.AccountRootPrincipal().account_id
                }
            },
        )

        sns_topic.add_to_resource_policy(sns_policy_statement)

        CfnOutput(self, "SNSTopicName", value=sns_topic.topic_name)
        return sns_topic

    def create_kms_key(self) -> kms.Key:
        """
        Create new KMS key and configure it for S3 object encryption
        """

        kms_key = kms.Key(
            self,
            "KMSKey",
            alias=f"alias/{Aws.STACK_NAME}/genai_key",
            enable_key_rotation=True,
            pending_window=Duration.days(7),
            removal_policy=RemovalPolicy.DESTROY,
        )
        kms_key.grant_encrypt_decrypt(
            iam.AnyPrincipal().with_conditions(
                {
                    "StringEquals": {
                        "kms:CallerAccount": f"{Aws.ACCOUNT_ID}",
                        "kms:ViaService": f"s3.{Aws.REGION}.amazonaws.com",
                    },
                }
            )
        )
        kms_key.grant_encrypt_decrypt(
            iam.ServicePrincipal(f"logs.{Aws.REGION}.amazonaws.com")
        )

        return kms_key

    def create_data_source_bucket(self, kms_key: kms.Key) -> s3.Bucket:
        """
        Create a s3 bucket to store audio file and extracted text file
        """
        audio_bucket = s3.Bucket(
            self,
            "SourceBucket",
            bucket_name=f"{Aws.STACK_NAME}-{Aws.ACCOUNT_ID}",
            versioned=True,
            removal_policy=RemovalPolicy.DESTROY,
            encryption=s3.BucketEncryption.KMS,
            encryption_key=kms_key,
            block_public_access=s3.BlockPublicAccess.BLOCK_ALL,
            enforce_ssl=True,
        )
        NagSuppressions.add_resource_suppressions(
            audio_bucket,
            suppressions=[
                {
                    "id": "AwsSolutions-S1",
                    "reason": "Demo app hence server access logs not enabled",
                }
            ],
        )

        CfnOutput(self, "S3BucketName", value=audio_bucket.bucket_name)
        return audio_bucket

    def upload_assets_to_bucket(
        self, audio_bucket: s3.Bucket, kms_key: kms.Key
    ) -> None:

        s3deploy.BucketDeployment(
            self,
            "AudioAsset",
            sources=[
                s3deploy.Source.asset(AUDIO_SAMPLES_PATH),
            ],
            destination_bucket=audio_bucket,
            destination_key_prefix="assets/audio_samples",
            server_side_encryption=s3deploy.ServerSideEncryption.AWS_KMS,
            server_side_encryption_aws_kms_key_id=kms_key.key_id,
        )

    def create_lambda_functions(self, bucket: s3.Bucket, kms_key: kms.Key):
        """
        Create lambda functions
        """

        bedrock_policy = iam.Policy(
            self,
            "BedrockPolicy",
            policy_name="AmazonBedrockAccessPolicy",
            statements=[
                iam.PolicyStatement(
                    actions=["bedrock:*"],
                    resources=[
                        f"arn:aws:bedrock:{Aws.REGION}::foundation-model/*"
                    ],  # Adjust as needed, specifying resources or using '*' for all resources
                    effect=iam.Effect.ALLOW,  # Specify ALLOW or DENY arn:aws:bedrock:us-west-2::foundation-model/anthropic.claude-v2
                )
            ],
        )
        s3_policy = iam.Policy(
            self,
            "S3Policy",
            policy_name="WriteToS3BucketPolicy",
            statements=[
                iam.PolicyStatement(
                    actions=["s3:*Object", "s3:ListBucket"],
                    resources=[
                        f"arn:aws:s3:::{bucket.bucket_name}/*",
                        f"arn:aws:s3:::{bucket.bucket_name}",
                    ],  # Adjust as needed, specifying resources or using '*' for all resources
                    effect=iam.Effect.ALLOW,  # Specify ALLOW or DENY arn:aws:bedrock:us-west-2::foundation-model/anthropic.claude-v2
                )
            ],
        )
        xray_policy = iam.Policy(
            self,
            "XRayPolicy",
            policy_name="XRayAccessPolicy",
            statements=[
                iam.PolicyStatement(
                    actions=["xray:PutTraceSegments", "xray:PutTelemetryRecords"],
                    resources=["*"],
                    effect=iam.Effect.ALLOW,
                )
            ],
        )

        # Create IAM role for Lambda Voice2Text function
        lambda_role = iam.Role(
            self,
            "LambdaRole",
            assumed_by=iam.ServicePrincipal("lambda.amazonaws.com"),
            managed_policies=[
                iam.ManagedPolicy.from_aws_managed_policy_name(
                    "service-role/AWSLambdaBasicExecutionRole"
                ),
                # Add a managed policy for Amazon Transcribe
                iam.ManagedPolicy.from_aws_managed_policy_name(
                    "AmazonTranscribeFullAccess"
                ),
            ],
        )
        lambda_role.attach_inline_policy(bedrock_policy)
        lambda_role.attach_inline_policy(s3_policy)
        lambda_role.attach_inline_policy(xray_policy)
        kms_key.grant_encrypt_decrypt(lambda_role)

        powertools_layer = lambda_.LayerVersion.from_layer_version_arn(
            self, id="PowertoolsLayer", layer_version_arn=POWERTOOLS_ARN
        )

        # create preprocessing lambda function
        lambda_function_preprocess = lambda_.Function(
            self,
            "PreprocessLambda",
            function_name=f"{Aws.STACK_NAME}-preprocess",
            description="Lambda code for triggering preprocessing",
            architecture=lambda_.Architecture.ARM_64,
            handler="preprocess.lambda_handler",
            runtime=lambda_.Runtime.PYTHON_3_12,
            code=lambda_.Code.from_asset(path.join(LAMBDA_PATH, "preprocess")),
            environment={
                "DATA_SOURCE_BUCKET_NAME": bucket.bucket_name,
                "POWERTOOLS_SERVICE_NAME": "app-preprocess",
                "POWERTOOLS_METRICS_NAMESPACE": f"{Aws.STACK_NAME}-ns",
                "POWERTOOLS_LOG_LEVEL": APP_LOG_LEVEL,
            },
            environment_encryption=kms_key,
            role=lambda_role,
            timeout=Duration.minutes(15),
            memory_size=1024,
            layers=[powertools_layer],
            tracing=lambda_.Tracing.ACTIVE,
        )

        # create voice2text lambda function
        lambda_function_transcribe = lambda_.Function(
            self,
            "TranscribeLambda",
            function_name=f"{Aws.STACK_NAME}-transcribe",
            description="Lambda code for triggering Amazon Transcribe batch transcription",
            architecture=lambda_.Architecture.ARM_64,
            handler="transcribe_batch.lambda_handler",
            runtime=lambda_.Runtime.PYTHON_3_12,
            code=lambda_.Code.from_asset(path.join(LAMBDA_PATH, "transcribe")),
            environment={
                "DATA_SOURCE_BUCKET_NAME": bucket.bucket_name,
                "POWERTOOLS_SERVICE_NAME": "app-transcribe",
                "POWERTOOLS_METRICS_NAMESPACE": f"{Aws.STACK_NAME}-ns",
                "POWERTOOLS_LOG_LEVEL": APP_LOG_LEVEL,
            },
            environment_encryption=kms_key,
            role=lambda_role,
            timeout=Duration.minutes(15),
            memory_size=1024,
            layers=[powertools_layer],
            tracing=lambda_.Tracing.ACTIVE,
        )

        # create lambda function for answer analysis using LLM (3)
        ecr_image_answer_analysis = lambda_.EcrImageCode.from_asset_image(
            directory=path.join(LAMBDA_PATH, "validate"),
            platform=Platform.LINUX_ARM64,
        )

        lambda_function_validate = lambda_.Function(
            self,
            "ValidationLambda",
            function_name=f"{Aws.STACK_NAME}-validate",
            description="Lambda code for validating answers",
            architecture=lambda_.Architecture.ARM_64,
            handler=lambda_.Handler.FROM_IMAGE,
            runtime=lambda_.Runtime.FROM_IMAGE,
            code=ecr_image_answer_analysis,
            environment={
                "DATA_SOURCE_BUCKET_NAME": bucket.bucket_name,
                "POWERTOOLS_SERVICE_NAME": "app-validate",
                "POWERTOOLS_METRICS_NAMESPACE": f"{Aws.STACK_NAME}-ns",
                "POWERTOOLS_LOG_LEVEL": APP_LOG_LEVEL,
            },
            environment_encryption=kms_key,
            role=lambda_role,
            timeout=Duration.minutes(15),
            memory_size=2048,
            tracing=lambda_.Tracing.ACTIVE,
        )

        # create lambda function for summary using LLM (7)
        ecr_image_summary = lambda_.EcrImageCode.from_asset_image(
            directory=path.join(LAMBDA_PATH, "summarize"),
            platform=Platform.LINUX_ARM64,
        )

        lambda_function_summarize = lambda_.Function(
            self,
            "SummaryLambda",
            function_name=f"{Aws.STACK_NAME}-summarize",
            description="Lambda code for summary",
            architecture=lambda_.Architecture.ARM_64,
            handler=lambda_.Handler.FROM_IMAGE,
            runtime=lambda_.Runtime.FROM_IMAGE,
            code=ecr_image_summary,
            environment={
                "DATA_SOURCE_BUCKET_NAME": bucket.bucket_name,
                "POWERTOOLS_SERVICE_NAME": "app-summarize",
                "POWERTOOLS_METRICS_NAMESPACE": f"{Aws.STACK_NAME}-ns",
                "POWERTOOLS_LOG_LEVEL": APP_LOG_LEVEL,
            },
            environment_encryption=kms_key,
            role=lambda_role,
            timeout=Duration.minutes(15),
            memory_size=2048,
            tracing=lambda_.Tracing.ACTIVE,
        )

        # create lambda function for document generation, using container (4)
        ecr_image_docgen = lambda_.EcrImageCode.from_asset_image(
            directory=path.join(LAMBDA_PATH, "generate"),
            platform=Platform.LINUX_ARM64,
        )

        lambda_function_generate = lambda_.Function(
            self,
            "GenerateLambda",
            function_name=f"{Aws.STACK_NAME}-generate",
            description="Lambda code for generating documents",
            architecture=lambda_.Architecture.ARM_64,
            handler=lambda_.Handler.FROM_IMAGE,
            runtime=lambda_.Runtime.FROM_IMAGE,
            code=ecr_image_docgen,
            environment={
                "DATA_SOURCE_BUCKET_NAME": bucket.bucket_name,
                "POWERTOOLS_SERVICE_NAME": "app-generate",
                "POWERTOOLS_METRICS_NAMESPACE": f"{Aws.STACK_NAME}-ns",
                "POWERTOOLS_LOG_LEVEL": APP_LOG_LEVEL,
            },
            environment_encryption=kms_key,
            role=lambda_role,
            timeout=Duration.minutes(15),
            memory_size=2048,
            tracing=lambda_.Tracing.ACTIVE,
        )

        return (
            lambda_function_preprocess,
            lambda_function_transcribe,
            lambda_function_validate,
            lambda_function_summarize,
            lambda_function_generate,
        )

    def create_step_functions_state_machine(
        self,
        kms_key: kms.Key,
        sns_topic: sns.Topic,
        lambda_function_preprocess: lambda_.Function,
        lambda_function_transcribe: lambda_.Function,
        lambda_function_validate: lambda_.Function,
        lambda_function_summarize: lambda_.Function,
        lambda_function_generate: lambda_.Function,
    ):
        """
        Create a Step Functions state machine using the JSON definition file
        """

        # Create new log group with the same name and add the dependencies.
        log_group = logs.LogGroup(
            self,
            "AppLogGroup",
            log_group_name=f"/aws/lambda/{Aws.STACK_NAME}-step-function",
            removal_policy=RemovalPolicy.DESTROY,
            retention=logs.RetentionDays.TWO_YEARS,
        )

        # Define the IAM role for the state machine
        role = iam.Role(
            self,
            id="StateMachineRole",
            role_name=f"{Aws.STACK_NAME}-state-machine-role",
            assumed_by=iam.ServicePrincipal("states.amazonaws.com"),
            managed_policies=[
                iam.ManagedPolicy.from_aws_managed_policy_name(
                    "service-role/AWSLambdaRole"
                ),
                iam.ManagedPolicy.from_aws_managed_policy_name(
                    "CloudWatchLogsFullAccess"
                ),
            ],
        )

        # Read the state machine definition from the JSON file
        with open(
            path.join(PARENT_DIR, "assets", "state_machine", "stepfunction.json"),
            "r",
            encoding="utf-8",
        ) as file:
            sm_definition = file.read()

        # Define the state machine
        state_machine = sfn.CfnStateMachine(
            self,
            id="StepFunction",
            state_machine_name=f"{Aws.STACK_NAME}-state-machine",
            role_arn=role.role_arn,
            definition_string=sm_definition,
            definition_substitutions={
                "sns_topic_arn": sns_topic.topic_arn,
                "preprocess_lambda_arn": lambda_function_preprocess.function_arn,
                "transcribe_batch_lambda_arn": lambda_function_transcribe.function_arn,
                "validate_lambda_arn": lambda_function_validate.function_arn,
                "summarize_lambda_arn": lambda_function_summarize.function_arn,
                "generate_lambda_arn": lambda_function_generate.function_arn,
            },
            tracing_configuration=sfn.CfnStateMachine.TracingConfigurationProperty(
                enabled=True
            ),
            logging_configuration=sfn.CfnStateMachine.LoggingConfigurationProperty(
                destinations=[
                    sfn.CfnStateMachine.LogDestinationProperty(
                        cloud_watch_logs_log_group=sfn.CfnStateMachine.CloudWatchLogsLogGroupProperty(
                            log_group_arn=log_group.log_group_arn
                        )
                    )
                ],
                include_execution_data=False,
                level="ALL",
            ),
        )

        sns_topic.grant_publish(role)
        kms_key.grant_encrypt_decrypt(role)
        CfnOutput(self, "StepFunctionARN", value=state_machine.attr_arn)
        return state_machine

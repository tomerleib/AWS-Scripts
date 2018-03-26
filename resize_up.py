import boto3
import json
import types
from retrying import retry
from botocore.exceptions import ClientError


class Instances(object):
    m3 = ["m3.medium", "m3.large", "m3.xlarge", "m3.2xlarge"]
    def __init__(self):
        pass
topic = "Your SNS Topic"

try:
    client = boto3.client('ec2')
    ec2_resource = boto3.resource('ec2')
    sns_client = boto3.client('sns')
# fun fact, if boto3 module fails, the sns topic won't be published..
except Exception as e:
    raise ("Error working with boto3 module")
if client is None:
    raise ('Error setting up boto3 client')
if ec2_resource is None:
    raise ("Error setting up boto3 resource")

@retry()
def publish_to_sns(instance_id,msg):
    sns_client.publish(Message="status of "+instance_id+" and "+ msg,TopicArn=topic)
    return



#Main function
def lambda_handler(event,context):
    alert = event['Records'][0]['Sns']['Message']
    if alert is None:
        publish_to_sns("No event was triggered")
        raise ("Error getting alert data")
    instance_id = alert['Trigger']['Dimensions'][0]['value']
    instance = ec2_resource.Instance(instance_id)
    ec2 = client.describe_instances(InstanceIds=[instance_id])
    instance_type = ec2['Reservations'][0]['Instances'][0]['InstanceType']
    instance_ip = ec2['Reservations'][0]['Instances'][0]['PublicIpAddress']
    tag_the_instance(instance_id,instance_type,instance_ip)
    #print("stopping the instance")
    stop_the_instance(instance_id)
    resize_the_instance(instance_id,instance_type)
    start_the_instance(instance_id)
    eip_associate(instance_id,instance_ip)
    get_instance_status(instance_id)



# creating the tags
@retry()
def tag_the_instance(instance_id,instance_type,instance_ip):
    tags = [{"Key": "orig-type", "Value": instance_type},
            {"Key": "EIP", "Value": instance_ip}]
    msg = "success"
    publish_to_sns(instance_id,msg)
    try:
         client.create_tags(Resources=[instance_id], Tags=tags)
    except (Exception, ClientError) as msg:
        publish_to_sns(instance_id,msg)
        raise

# Stopping the instance
@retry(stop_max_attempt_number=5)
def stop_the_instance(instance_id):
    try:
        client.stop_instances(InstanceIds=[instance_id])
        waiter = client.get_waiter('instance_stopped')
        waiter.wait(InstanceIds=[instance_id])
        print("check if instance is stopped-1")
    except (Exception,ClientError) as msg:
        publish_to_sns(instance_id,msg)
        raise msg
    print("check if instance is stopped-2")


#resizing the instance
@retry()
def resize_the_instance (instance_id,instance_type):
    instance_index = Instances.m3.index(instance_type)
    resize_instance = Instances.m3[instance_index + 1]
    print(resize_instance)
    if resize_instance is None:
        msg = "error with resize_instance var"
        publish_to_sns(instance_id,msg)
        return
    else:
        try:
            client.modify_instance_attribute(
                InstanceId=instance_id, Attribute='instanceType', Value=resize_instance)
            msg = "resize successful"
            publish_to_sns(instance_id,msg)
        except (Exception,ClientError) as msg:
                publish_to_sns(instance_id,msg)
                pass


#start the instance
@retry(stop_max_attempt_number=5)
def start_the_instance(instance_id):
    try:
        client.start_instances(InstanceIds=[instance_id])
        waiter = client.get_waiter('instance_running')
        waiter.wait(InstanceIds=[instance_id])
    except (Exception,ClientError,TypeError) as msg:
        publish_to_sns(instance_id,msg)



#Associate EIP to the instance
@retry(stop_max_attempt_number=5)
def eip_associate(instance_id,instance_ip):
    try:
        client.associate_address(
            InstanceId=instance_id, PublicIp=instance_ip)
    except (ClientError, Exception) as msg:
        publish_to_sns(instance_id,msg)



#Get instance status
@retry(stop_max_attempt_number=5)
def get_instance_status(instance_id):
    status = client.describe_instance_status(InstanceIds=[instance_id])
    if 'Failed' in status:
        msg = "Current state have errors " + status
        publish_to_sns(instance_id,msg)
        raise ("Instance state is unhealthy")
    else:
        msg = ("Instance state is healthy")
        publish_to_sns(instance_id,msg)

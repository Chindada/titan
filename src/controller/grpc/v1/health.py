import logging
from datetime import datetime

from apscheduler.schedulers.background import BackgroundScheduler
from cron_converter import Cron
from google.protobuf import empty_pb2
from panther.health import health_pb2_grpc

logging.getLogger("apscheduler").propagate = False


class RPCHealth(health_pb2_grpc.HealthInterfaceServicer):
    def __init__(
        self,
        stop_function=None,
    ):
        if stop_function is None:
            raise ValueError("stop_function must be provided")
        self.stop_function = stop_function
        self.scheduler()

    def HealthChannel(self, request_iterator, _):
        try:
            for _ in request_iterator:
                yield empty_pb2.Empty()
        except:
            self.stop_function()

    def scheduler(self):
        scheduler = BackgroundScheduler()
        cron_instance_1 = Cron("20 8 * * *")
        cron_instance_2 = Cron("40 14 * * *")
        now = datetime.now()
        schedule_1 = cron_instance_1.schedule(now).next()
        schedule_2 = cron_instance_2.schedule(now).next()
        scheduler.add_job(
            func=self.stop_function,
            trigger="date",
            run_date=schedule_1,
            id="stop_job_1",
        )
        scheduler.add_job(
            func=self.stop_function,
            trigger="date",
            run_date=schedule_2,
            id="stop_job_2",
        )
        scheduler.start()

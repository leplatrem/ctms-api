import glob
import json
import os
import sys
import time

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from ctms.app import _process_stripe_object

from ctms.ingest_stripe import (
    StripeIngestActions,
    StripeIngestUnknownObjectError,
    ingest_stripe_object,
)


def main(argv):
    payloads_path = argv[1]

    payloads_paths = glob.glob(os.path.join(payloads_path, "*.json"))

    dsn = os.getenv("CTMS_DB_URL", "postgresql://ctmsuser:ctmsuser@localhost/ctms")
    echo = True if "-v" in argv else ("debug" if "-vv" in argv else False)
    engine = create_engine(dsn, echo=echo)

    Session = sessionmaker(bind=engine)
    db_session = Session()

    i = 0
    while True:
        payload_path = payloads_paths[i % len(payloads_paths)]

        start_time = time.time()

        with open(payload_path) as f:
            payload = json.load(f)

        for item in payload.values():
            try:
                email_id, trace_email, fxa_conflict, item_actions = _process_stripe_object(
                    db_session, item
                )
            except StripeIngestUnknownObjectError as exception:
                print(exception)
            except (KeyError, ValueError, TypeError) as exception:
                print(exception)

        end_time = time.time()
        if i % 100 == 0:
            print(end_time - start_time, "msec")

        i += 1

    db_session.close()


if __name__ == "__main__":
    main(sys.argv)

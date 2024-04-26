select
	ar.status,
	count(*) as requests_count
from application_requests as ar
where 1=1
	and ar.log_message_chat_id is not null -- only requests submitted to the staff
	and ar.status is not null -- only requests that have been evaluated
group by ar.status;

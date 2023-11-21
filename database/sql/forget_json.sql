update admin_messages
set message_json = NULL;

update application_requests
set log_message_json = NULL, staff_message_json = NULL;

update description_messages
set message_json = NULL, log_message_json = NULL;

update private_chat_messages
set message_json = NULL;

update staff_chat_messages
set message_json = NULL;

update user_messages
set message_json = NULL;

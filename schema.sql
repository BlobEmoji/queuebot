create table if not exists suggestions (
    idx serial primary key,
    user_id bigint,
    council_message_id bigint,
    public_message_id bigint,
    emoji_id bigint,
    emoji_name text,
    upvotes int default 0,
    downvotes int default 0
);

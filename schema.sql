create table if not exists suggestions (
    -- emoji id
    idx serial primary key,

    -- user that submitted the emoji
    user_id bigint,

    -- message id in the #council-queue
    council_message_id bigint,

    -- message id in the #approval-queue
    public_message_id bigint,

    -- emoji data
    emoji_id bigint,
    emoji_name text,

    -- votes
    upvotes int default 0,
    downvotes int default 0
);

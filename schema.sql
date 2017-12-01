
-- migration compat, remove when suitable time has passed
ALTER TABLE IF EXISTS suggestions
    -- timestamps
    ADD COLUMN IF NOT EXISTS submission_time TIMESTAMP, -- when this was submitted
    ADD COLUMN IF NOT EXISTS validation_time TIMESTAMP, -- when this was approved or denied

    -- validation
    ADD COLUMN IF NOT EXISTS council_approved BOOLEAN, -- was the emoji approved by Council?
    ADD COLUMN IF NOT EXISTS forced_reason TEXT, -- reason for Council validation being forced.
    ADD COLUMN IF NOT EXISTS forced_by BIGINT -- ID of the user who forced this. if not forced, this is NULL.
;


CREATE TABLE IF NOT EXISTS suggestions (
    -- suggestion id
    idx SERIAL PRIMARY KEY,

    -- user that submitted the emoji
    user_id BIGINT,

    -- message id in the #council-queue
    council_message_id BIGINT,

    -- message id in the #approval-queue
    public_message_id BIGINT,

    -- emoji data
    emoji_id BIGINT,
    emoji_name TEXT,

    -- votes
    upvotes INT DEFAULT 0,
    downvotes INT DEFAULT 0,

    -- timestamps
    submission_time TIMESTAMP, -- when this was submitted
    validation_time TIMESTAMP, -- when this was approved or denied

    -- validation
    council_approved BOOLEAN, -- was the emoji approved by Council?
    forced_reason TEXT, -- reason for Council validation being forced.
    forced_by BIGINT -- ID of the user who forced this. if not forced, this is NULL.
);

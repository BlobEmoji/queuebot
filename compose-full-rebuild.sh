#!/bin/bash

echo -e "\033[0mThis script will:"
echo -e "- \033[1;31mDelete\033[0m the current compose build (if it exists)"
echo -e "- \033[1;31mDelete\033[0m any non-referenced inactive compose builds (if they exist)"
echo -e "- \033[1;31mDelete\033[0m \033[0;36m./data\033[0m, the PostgreSQL data folder (if it exists)"
echo -e "- \033[1;34mBuild\033[0m this repo state's compose build, disabling cache mode and obtaining images as necessary."
echo -e "- \033[1;32mRun\033[0m this compose build in an attached state"
echo -e "\nIf you are VERY sure that this is what you want to do, please type:\n'\033[0;37myes pls\033[0m'"

read -p "> " -r
echo
if [[ $REPLY = "yes pls" ]]
then
    docker-compose down &&
    docker-compose rm -f &&
    rm -rf data/ &&
    docker-compose build --no-cache &&
    docker-compose up "$@"
else
    echo "Response did not match pattern, aborting."
    exit 2
fi

# Review:

CLAUDE.md
README.md

create a brew tap - see claude

publish to r/stuff - see claude

differenet approach - let me know thoughts before implementing -

1. does eza already have an option to flag recently-edited files? I like that generally. so, have an option to highligh anything (default cyan?) if modified in last 60 sec (tunable)
2. that covers the magic comment case. though do we highlight the filename or the comment hmmm
3. for lsc --set, can we store LSC STATE (hidden shell var? or .. ?) that is an dict of paths+timestamps of files with recently modified comments -then on a lsc run, check that array and highlight anything with timestamp in last 60 sec - and evict anythign older from the array

is that sensible?
the not-byte-identical objection doesn't really apply - that was only ever when NO comments are present.  REMOVING a comment wouldn't add a file to the dict.

thoughts?

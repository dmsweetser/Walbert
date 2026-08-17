rm -r ./instance/config.json 
rm -r ./instance/conversations/*
rm -r ./instance/walbert.*
rm -r ./walbert_prompt_*
rm -r ./walbert_response_*
chmod +x ./_install.sh
./_install.sh
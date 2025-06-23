# TITAN

## Command

```sh
# stop old container
docker stop titan -t 600
docker system prune --volumes -f
# run
docker pull ghcr.io/chindada/titan:v1.0
docker run -d \
    --restart always \
    --name titan \
    -v $(pwd)/data/config.yaml:/usr/share/app/titan/data/config.yaml \
    -p 80:80 \
    -p 443:443 \
    ghcr.io/chindada/titan:v1.0
docker logs -f titan
```

```sh
pip install git+ssh://git@github.com/Chindada/panther.git@v1.0
```

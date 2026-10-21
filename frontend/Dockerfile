FROM node:22-slim

WORKDIR /srv

# npm ci installs exactly what the lockfile pins, as CI does, and fails if
# package.json and the lockfile disagree (LESSONS.md 4).
COPY package.json package-lock.json ./
RUN npm ci

COPY . .

EXPOSE 5173
CMD ["npm", "run", "dev", "--", "--host", "0.0.0.0"]

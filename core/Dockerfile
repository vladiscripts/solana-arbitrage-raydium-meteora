FROM python:3.9-slim

# Set the working directory
WORKDIR /usr/src/main

# Copy the current directory contents into the container
COPY . .

# Install the necessary Python packages
RUN pip install --no-cache-dir -r requirements.txt

# Expose port 80 to the outside world
EXPOSE 80

# Run the app when the container launches
CMD ["python", "main.py"]

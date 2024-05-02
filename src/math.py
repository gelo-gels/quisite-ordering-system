# Function to read the current number from a file
def read_current_number():
    try:
        with open('storage_number.txt', 'r') as file:
            return int(file.read().strip())
    except FileNotFoundError:
        return 1000  # Default starting number if file doesn't exist

# Function to write the current number to a file
def write_current_number(number):
    with open('storage_number.txt', 'w') as file:
        file.write(str(number))

# Function to generate a three-digit number
def unique_order_number():
    current_number = read_current_number()
    if current_number == 9999:
        current_number = 1000  # Reset to 1000 when it reaches 9999
    else:
        current_number += 1  # Increment the current number
    write_current_number(current_number)  # Save the updated current number to file
    return current_number
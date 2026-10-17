from rp_runner.server import serve

from rp_mcuboot.family import McubootFamily

if __name__ == "__main__":
    serve(McubootFamily())

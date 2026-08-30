class AgentState:
    
    def __init__(self):

        # ====================================================
        # CURRENT USER
        # ====================================================

        self.current_user_id = None

        self.current_username = None

        self.current_user_name = None

        # ====================================================
        # CURRENT TASK
        # ====================================================

        self.goal = ""

        # ====================================================
        # REQUESTED BOOK
        # ====================================================

        self.requested_book = None

        self.requested_book_id = None

        self.requested_book_available = None

        # ====================================================
        # ALTERNATIVE BOOK
        # ====================================================

        self.alternative_book = None

        self.alternative_book_id = None

        # ====================================================
        # LOAN INFORMATION
        # ====================================================

        self.borrowed_at = None

        self.due_date = None

        self.returned_at = None

        # ====================================================
        # OVERDUE INFORMATION
        # ====================================================

        self.is_overdue = False

        self.late_days = 0

        # ====================================================
        # FINE INFORMATION
        # ====================================================

        self.fine_amount = 0.0

        self.fine_paid = False

        self.fine_paid_at = None

        # ====================================================
        # PAYMENT INFORMATION
        # ====================================================

        self.payment_amount = 0.0

        self.payment_status = None

        # ====================================================
        # TASK STATUS
        # ====================================================

        self.completed = False

        self.waiting_for_confirmation = False

        # ====================================================
        # LAST ACTION
        # ====================================================

        self.last_action = None


    # ========================================================
    # CURRENT USER
    # ========================================================

    def set_current_user(
        self,
        user_id=None,
        username=None,
        full_name=None
    ):

        self.current_user_id = user_id

        self.current_username = username

        self.current_user_name = full_name


    def is_logged_in(self):

        return self.current_user_id is not None


    def clear_current_user(self):

        self.current_user_id = None

        self.current_username = None

        self.current_user_name = None


    # ========================================================
    # REQUESTED BOOK
    # ========================================================

    def update_requested_book(
        self,
        book
    ):

        if not isinstance(
            book,
            dict
        ):

            return

        self.requested_book = book.get(
            "title"
        )

        self.requested_book_id = book.get(
            "id"
        )

        if "available" in book:

            self.requested_book_available = bool(
                book.get(
                    "available"
                )
            )


    # ========================================================
    # UPDATE REQUESTED BOOK FROM TOOL RESULT
    # ========================================================

    def update_requested_book_from_result(
        self,
        result
    ):
        """
        Synchronize book information returned by a tool.

        This is particularly important when
        check_book_availability() is called directly.
        """

        if not isinstance(
            result,
            dict
        ):

            return

        book_id = result.get(
            "id"
        )

        title = result.get(
            "title"
        )

        if book_id is None:

            return

        if not title:

            return

        self.requested_book_id = book_id

        self.requested_book = title

        if "available" in result:

            self.requested_book_available = bool(
                result.get(
                    "available"
                )
            )


    # ========================================================
    # AVAILABILITY
    # ========================================================

    def update_requested_book_availability(
        self,
        available
    ):

        if available is None:

            self.requested_book_available = None

            return

        self.requested_book_available = bool(
            available
        )


    # ========================================================
    # ALTERNATIVE BOOK
    # ========================================================

    def set_alternative(
        self,
        book
    ):

        if not isinstance(
            book,
            dict
        ):

            return

        self.alternative_book = book.get(
            "title"
        )

        self.alternative_book_id = book.get(
            "id"
        )


    # ========================================================
    # LOAN DATES
    # ========================================================

    def set_loan_dates(
        self,
        borrowed_at=None,
        due_date=None,
        returned_at=None
    ):

        self.borrowed_at = borrowed_at

        self.due_date = due_date

        self.returned_at = returned_at


    # ========================================================
    # OVERDUE
    # ========================================================

    def set_overdue_status(
        self,
        is_overdue=False,
        late_days=0
    ):

        self.is_overdue = bool(
            is_overdue
        )

        try:

            self.late_days = max(
                0,
                int(late_days)
            )

        except (
            TypeError,
            ValueError
        ):

            self.late_days = 0


    # ========================================================
    # FINE
    # ========================================================

    def set_fine(
        self,
        fine_amount=0.0,
        fine_paid=False,
        fine_paid_at=None
    ):

        try:

            self.fine_amount = float(
                fine_amount
            )

        except (
            TypeError,
            ValueError
        ):

            self.fine_amount = 0.0

        self.fine_paid = bool(
            fine_paid
        )

        self.fine_paid_at = fine_paid_at


    # ========================================================
    # PAYMENT
    # ========================================================

    def set_payment(
        self,
        payment_amount=0.0,
        payment_status=None
    ):

        try:

            self.payment_amount = float(
                payment_amount
            )

        except (
            TypeError,
            ValueError
        ):

            self.payment_amount = 0.0

        self.payment_status = payment_status


    # ========================================================
    # COMPLETE
    # ========================================================

    def complete(self):

        self.completed = True

        self.waiting_for_confirmation = False


    # ========================================================
    # CONFIRMATION
    # ========================================================

    def wait_for_confirmation(self):

        self.waiting_for_confirmation = True


    def clear_confirmation(self):

        self.waiting_for_confirmation = False


    # ========================================================
    # RESET CURRENT TASK
    # ========================================================

    def reset_task(self):

        self.goal = ""

        self.requested_book = None

        self.requested_book_id = None

        self.requested_book_available = None

        self.alternative_book = None

        self.alternative_book_id = None

        self.borrowed_at = None

        self.due_date = None

        self.returned_at = None

        self.is_overdue = False

        self.late_days = 0

        self.fine_amount = 0.0

        self.fine_paid = False

        self.fine_paid_at = None

        self.payment_amount = 0.0

        self.payment_status = None

        self.completed = False

        self.waiting_for_confirmation = False

        self.last_action = None


    # ========================================================
    # RESET ALL
    # ========================================================

    def reset_all(self):

        self.clear_current_user()

        self.reset_task()


    # ========================================================
    # INTERNAL STATE
    # ========================================================

    def show(self):

        return {

            "current_user_id":
                self.current_user_id,

            "current_username":
                self.current_username,

            "current_user_name":
                self.current_user_name,

            "goal":
                self.goal,

            "requested_book":
                self.requested_book,

            "requested_book_id":
                self.requested_book_id,

            "requested_book_available":
                self.requested_book_available,

            "alternative_book":
                self.alternative_book,

            "alternative_book_id":
                self.alternative_book_id,

            "borrowed_at":
                self.borrowed_at,

            "due_date":
                self.due_date,

            "returned_at":
                self.returned_at,

            "is_overdue":
                self.is_overdue,

            "late_days":
                self.late_days,

            "fine_amount":
                self.fine_amount,

            "fine_paid":
                self.fine_paid,

            "fine_paid_at":
                self.fine_paid_at,

            "payment_amount":
                self.payment_amount,

            "payment_status":
                self.payment_status,

            "completed":
                self.completed,

            "waiting_for_confirmation":
                self.waiting_for_confirmation,

            "last_action":
                self.last_action
        }